"""Deployment-oriented data functions: YAML apply, Helm runner Jobs,
and OpenShift build creation/start helpers.
"""

import json
import re
import shlex
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import yaml
from fastapi import HTTPException
from kubernetes import client
from kubernetes.client.rest import ApiException

from audit import audited
from config import (
    DEFAULT_HELM_RUNNER_IMAGE,
    OPENSHIFT_BUILD_GROUP,
    OPENSHIFT_BUILD_VERSION,
    batch_v1,
    core_v1,
    custom_objects,
)
from errors import api_error
from summarizers import summarize_build, summarize_build_config, summarize_job
from validation import validated_dns_label, validated_name

SAFE_HELM_CHART_RE = re.compile(r"^[A-Za-z0-9._:/@+-][A-Za-z0-9._:/@+/-]*$")
SAFE_TIMEOUT_RE = re.compile(r"^[0-9]+[smh]$")


def _decode_response(response: Any) -> Dict[str, Any]:
    if isinstance(response, dict):
        return response
    data = getattr(response, "data", response)
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if isinstance(data, str) and data:
        return json.loads(data)
    return {}


def _api_version_parts(api_version: str) -> Tuple[str, str]:
    if "/" not in api_version:
        return "", api_version
    group, version = api_version.split("/", 1)
    return group, version


def _discover_resource(api_version: str, kind: str) -> Dict[str, Any]:
    group, version = _api_version_parts(api_version)
    path = f"/api/{version}" if not group else f"/apis/{group}/{version}"
    response = custom_objects.api_client.call_api(
        path,
        "GET",
        response_types_map={200: "object"},
        auth_settings=["BearerToken"],
        _return_http_data_only=True,
        _preload_content=False,
    )
    resources = _decode_response(response).get("resources", [])
    for resource in resources:
        if resource.get("kind") == kind and "/" not in resource.get("name", ""):
            return resource
    raise HTTPException(
        status_code=400,
        detail=f"API resource for {api_version}/{kind} was not found",
    )


def _resource_collection_path(
    api_version: str, plural: str, namespace: Optional[str]
) -> str:
    group, version = _api_version_parts(api_version)
    escaped_plural = quote(plural, safe="")
    if namespace:
        escaped_ns = quote(namespace, safe="")
        if group:
            return f"/apis/{group}/{version}/namespaces/{escaped_ns}/{escaped_plural}"
        return f"/api/{version}/namespaces/{escaped_ns}/{escaped_plural}"
    if group:
        return f"/apis/{group}/{version}/{escaped_plural}"
    return f"/api/{version}/{escaped_plural}"


def _manifest_identity(obj: Dict[str, Any]) -> Dict[str, Optional[str]]:
    metadata = obj.get("metadata") or {}
    return {
        "api_version": obj.get("apiVersion"),
        "kind": obj.get("kind"),
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
    }


@audited("apply_yaml")
def apply_yaml_data(
    manifest: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    field_manager: str = "mcp-openshift",
) -> Dict[str, Any]:
    default_namespace = (
        validated_dns_label(namespace, "namespace") if namespace is not None else None
    )
    try:
        documents = [doc for doc in yaml.safe_load_all(manifest) if doc]
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}")

    if not documents:
        raise HTTPException(
            status_code=400, detail="manifest must contain at least one object"
        )

    applied: List[Dict[str, Any]] = []
    query_params = [("fieldManager", field_manager)]
    if dry_run:
        query_params.append(("dryRun", "All"))

    for obj in documents:
        if not isinstance(obj, dict):
            raise HTTPException(
                status_code=400, detail="Each YAML document must be an object"
            )
        api_version = obj.get("apiVersion")
        kind = obj.get("kind")
        metadata = obj.setdefault("metadata", {})
        name = metadata.get("name")
        if not api_version or not kind or not name:
            raise HTTPException(
                status_code=400,
                detail="Each YAML object must include apiVersion, kind, and metadata.name",
            )

        resource = _discover_resource(api_version, kind)
        object_name = validated_name(name)
        object_namespace = metadata.get("namespace") or default_namespace
        if resource.get("namespaced"):
            if not object_namespace:
                raise HTTPException(
                    status_code=400,
                    detail=f"{kind} is namespaced; provide metadata.namespace or namespace",
                )
            object_namespace = validated_dns_label(object_namespace, "namespace")
            metadata["namespace"] = object_namespace
        else:
            object_namespace = None

        collection_path = _resource_collection_path(
            api_version, resource["name"], object_namespace
        )
        path = f"{collection_path}/{quote(object_name, safe='')}"
        try:
            response = custom_objects.api_client.call_api(
                path,
                "PATCH",
                query_params=query_params,
                header_params={"Content-Type": "application/apply-patch+yaml"},
                body=obj,
                response_types_map={200: "object", 201: "object"},
                auth_settings=["BearerToken"],
                _return_http_data_only=True,
                _preload_content=False,
            )
            result = _decode_response(response)
            applied.append(
                {
                    "status": "dry_run" if dry_run else "applied",
                    **_manifest_identity(result or obj),
                }
            )
        except ApiException as e:
            raise api_error(e)

    return {
        "status": "dry_run" if dry_run else "applied",
        "count": len(applied),
        "items": applied,
    }


def _validate_helm_inputs(release_name: str, chart: str, namespace: str, timeout: str):
    validated_name(release_name)
    validated_dns_label(namespace, "namespace")
    if not chart or not SAFE_HELM_CHART_RE.match(chart):
        raise HTTPException(
            status_code=400, detail="chart contains unsupported characters"
        )
    if not SAFE_TIMEOUT_RE.match(timeout):
        raise HTTPException(
            status_code=400, detail="timeout must look like 10m, 60s, or 1h"
        )


@audited("deploy_helm")
def deploy_helm_data(
    release_name: str,
    chart: str,
    namespace: str,
    repo_url: Optional[str] = None,
    chart_version: Optional[str] = None,
    values: Optional[Dict[str, Any]] = None,
    values_yaml: Optional[str] = None,
    create_namespace: bool = True,
    wait: bool = False,
    timeout: str = "10m",
    job_namespace: str = "mcp-server",
    job_name: Optional[str] = None,
    image: Optional[str] = None,
    service_account_name: str = "mcp-openshift",
    ttl_seconds_after_finished: int = 86400,
    active_deadline_seconds: int = 1800,
) -> Dict[str, Any]:
    _validate_helm_inputs(release_name, chart, namespace, timeout)
    validated_job_namespace = validated_dns_label(job_namespace, "job namespace")
    release = validated_name(release_name)
    target_namespace = validated_dns_label(namespace, "namespace")
    helm_image = image or DEFAULT_HELM_RUNNER_IMAGE
    generated_job_name = validated_name(
        job_name
        or f"mcp-helm-{release}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    merged_values_yaml = values_yaml
    if values:
        generated_values = yaml.safe_dump(values, sort_keys=False)
        merged_values_yaml = (
            f"{values_yaml.rstrip()}\n{generated_values}"
            if values_yaml
            else generated_values
        )

    chart_ref = f"mcp/{chart}" if repo_url else chart
    helm_args = [
        "helm",
        "upgrade",
        "--install",
        release,
        chart_ref,
        "--namespace",
        target_namespace,
        "--timeout",
        timeout,
    ]
    if create_namespace:
        helm_args.append("--create-namespace")
    if wait:
        helm_args.append("--wait")
    if chart_version:
        helm_args.extend(["--version", chart_version])
    if merged_values_yaml:
        helm_args.extend(["-f", "/tmp/mcp-values.yaml"])

    script_lines = ["set -eu"]
    if repo_url:
        if "\n" in repo_url:
            raise HTTPException(
                status_code=400, detail="repo_url must be a single line"
            )
        script_lines.extend(['helm repo add mcp "$HELM_REPO_URL"', "helm repo update"])
    if merged_values_yaml:
        script_lines.append('printf "%s" "$HELM_VALUES_YAML" > /tmp/mcp-values.yaml')
    script_lines.append(shlex.join(helm_args))

    env = []
    if repo_url:
        env.append(client.V1EnvVar(name="HELM_REPO_URL", value=repo_url))
    if merged_values_yaml:
        env.append(client.V1EnvVar(name="HELM_VALUES_YAML", value=merged_values_yaml))

    job = client.V1Job(
        metadata=client.V1ObjectMeta(
            name=generated_job_name,
            namespace=validated_job_namespace,
            labels={
                "app.kubernetes.io/name": "mcp-helm-deploy",
                "app.kubernetes.io/part-of": "mcp-server",
                "mcp.openshift.io/helm-release": release,
            },
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=ttl_seconds_after_finished,
            active_deadline_seconds=active_deadline_seconds,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app.kubernetes.io/name": "mcp-helm-deploy",
                        "job-name": generated_job_name,
                    }
                ),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    service_account_name=validated_name(service_account_name),
                    containers=[
                        client.V1Container(
                            name="helm",
                            image=helm_image,
                            image_pull_policy="IfNotPresent",
                            command=["/bin/sh", "-lc", "\n".join(script_lines)],
                            env=env,
                        )
                    ],
                ),
            ),
        ),
    )
    try:
        result = batch_v1.create_namespaced_job(validated_job_namespace, body=job)
        return {
            "status": "created",
            "job": summarize_job(result),
            "release_name": release,
            "namespace": target_namespace,
            "chart": chart,
            "repo_url": repo_url,
            "image": helm_image,
            "logs_tool": "get_helm_deploy_logs",
        }
    except ApiException as e:
        raise api_error(e)


def get_helm_deploy_logs_data(namespace: str, job_name: str) -> Dict[str, Any]:
    validated_namespace = validated_dns_label(namespace, "namespace")
    validated_job = validated_name(job_name)
    try:
        pods = core_v1.list_namespaced_pod(
            validated_namespace, label_selector=f"job-name={validated_job}"
        )
        if not pods.items:
            return {
                "job_name": job_name,
                "namespace": namespace,
                "pods": [],
                "logs": "",
            }
        pod = pods.items[0]
        logs = core_v1.read_namespaced_pod_log(
            pod.metadata.name, validated_namespace, container="helm"
        )
        return {
            "job_name": job_name,
            "namespace": namespace,
            "pod_name": pod.metadata.name,
            "logs": logs,
        }
    except ApiException as e:
        raise api_error(e, "Helm deploy pod not found")


@audited("start_build_config")
def start_build_config_data(
    namespace: str,
    build_config_name: str,
    env: Optional[Dict[str, str]] = None,
    commit: Optional[str] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    validated_namespace = validated_dns_label(namespace, "namespace")
    validated_bc = validated_name(build_config_name)
    body: Dict[str, Any] = {
        "kind": "BuildRequest",
        "apiVersion": f"{OPENSHIFT_BUILD_GROUP}/{OPENSHIFT_BUILD_VERSION}",
        "metadata": {"name": validated_bc},
    }
    if env:
        body["env"] = [{"name": key, "value": value} for key, value in env.items()]
    if commit or message:
        body["revision"] = {"git": {}}
        if commit:
            body["revision"]["git"]["commit"] = commit
        if message:
            body["revision"]["git"]["message"] = message

    path = (
        f"/apis/{OPENSHIFT_BUILD_GROUP}/{OPENSHIFT_BUILD_VERSION}/namespaces/"
        f"{quote(validated_namespace, safe='')}/buildconfigs/"
        f"{quote(validated_bc, safe='')}/instantiate"
    )
    try:
        response = custom_objects.api_client.call_api(
            path,
            "POST",
            header_params={"Content-Type": "application/json"},
            body=body,
            response_types_map={200: "object", 201: "object"},
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _preload_content=False,
        )
        return {
            "status": "started",
            "build": summarize_build(_decode_response(response)),
        }
    except ApiException as e:
        raise api_error(e, "BuildConfig not found")


@audited("create_build")
def create_build_data(namespace: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    validated_namespace = validated_dns_label(namespace, "namespace")
    if manifest.get("kind") != "Build":
        raise HTTPException(status_code=400, detail="manifest.kind must be Build")
    metadata = manifest.setdefault("metadata", {})
    if not metadata.get("name"):
        raise HTTPException(
            status_code=400, detail="manifest.metadata.name is required"
        )
    metadata["name"] = validated_name(metadata["name"])
    metadata["namespace"] = validated_namespace
    try:
        result = custom_objects.create_namespaced_custom_object(
            OPENSHIFT_BUILD_GROUP,
            OPENSHIFT_BUILD_VERSION,
            validated_namespace,
            "builds",
            manifest,
        )
        return {"status": "created", "build": summarize_build(result)}
    except ApiException as e:
        raise api_error(e)


@audited("create_build_config")
def create_build_config_data(
    namespace: str, manifest: Dict[str, Any]
) -> Dict[str, Any]:
    validated_namespace = validated_dns_label(namespace, "namespace")
    if manifest.get("kind") != "BuildConfig":
        raise HTTPException(status_code=400, detail="manifest.kind must be BuildConfig")
    metadata = manifest.setdefault("metadata", {})
    if not metadata.get("name"):
        raise HTTPException(
            status_code=400, detail="manifest.metadata.name is required"
        )
    metadata["name"] = validated_name(metadata["name"])
    metadata["namespace"] = validated_namespace
    try:
        result = custom_objects.create_namespaced_custom_object(
            OPENSHIFT_BUILD_GROUP,
            OPENSHIFT_BUILD_VERSION,
            validated_namespace,
            "buildconfigs",
            manifest,
        )
        return {"status": "created", "build_config": summarize_build_config(result)}
    except ApiException as e:
        raise api_error(e)
