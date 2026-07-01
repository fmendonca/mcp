"""Data functions for OLM (Operator Lifecycle Manager) resources —
Subscriptions, OperatorGroups, installed operators (CSVs), CatalogSources,
generic operator install helpers — and the must-gather Job lifecycle.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from kubernetes import client
from kubernetes.client.rest import ApiException

from config import (
    DEFAULT_MUST_GATHER_IMAGE,
    OLM_GROUP,
    OLM_OPERATOR_GROUP_VERSION,
    OLM_VERSION,
    batch_v1,
    core_v1,
    custom_objects,
)
from crd_helpers import _list_namespaced
from errors import api_error
from summarizers import (
    summarize_catalog_source,
    summarize_csv,
    summarize_job,
    summarize_operator_group,
    summarize_subscription,
)
from validation import validated_dns_label, validated_name


# OLM
def list_subscriptions_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OLM_GROUP,
        OLM_VERSION,
        namespace,
        "subscriptions",
        summarize_subscription,
        "SubscriptionList",
    )


def list_installed_operators_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OLM_GROUP,
        OLM_VERSION,
        namespace,
        "clusterserviceversions",
        summarize_csv,
        "ClusterServiceVersionList",
    )


def list_catalog_sources_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OLM_GROUP,
        OLM_VERSION,
        namespace,
        "catalogsources",
        summarize_catalog_source,
        "CatalogSourceList",
    )


def create_operator_group_data(
    namespace: str,
    name: str = "mcp-operator-group",
    target_namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validated_namespace = validated_dns_label(namespace, "namespace")
    validated_targets = (
        [validated_dns_label(n, "target namespace") for n in target_namespaces]
        if target_namespaces
        else None
    )
    body: Dict[str, Any] = {
        "apiVersion": f"{OLM_GROUP}/{OLM_OPERATOR_GROUP_VERSION}",
        "kind": "OperatorGroup",
        "metadata": {"name": validated_name(name), "namespace": validated_namespace},
        "spec": {},
    }
    if validated_targets is not None:
        body["spec"]["targetNamespaces"] = validated_targets

    try:
        result = custom_objects.create_namespaced_custom_object(
            OLM_GROUP,
            OLM_OPERATOR_GROUP_VERSION,
            validated_namespace,
            "operatorgroups",
            body,
        )
        return {"status": "created", "operator_group": summarize_operator_group(result)}
    except ApiException as e:
        raise api_error(e)


def create_olm_subscription_data(
    namespace: str,
    package_name: str,
    channel: str = "stable",
    source: str = "redhat-operators",
    source_namespace: str = "openshift-marketplace",
    install_plan_approval: str = "Automatic",
    name: Optional[str] = None,
    starting_csv: Optional[str] = None,
) -> Dict[str, Any]:
    subscription_name = validated_name(name or package_name)
    body: Dict[str, Any] = {
        "apiVersion": f"{OLM_GROUP}/{OLM_VERSION}",
        "kind": "Subscription",
        "metadata": {
            "name": subscription_name,
            "namespace": validated_dns_label(namespace, "namespace"),
        },
        "spec": {
            "channel": channel,
            "installPlanApproval": install_plan_approval,
            "name": package_name,
            "source": source,
            "sourceNamespace": source_namespace,
        },
    }
    if starting_csv:
        body["spec"]["startingCSV"] = starting_csv

    try:
        result = custom_objects.create_namespaced_custom_object(
            OLM_GROUP,
            OLM_VERSION,
            validated_dns_label(namespace, "namespace"),
            "subscriptions",
            body,
        )
        return {"status": "created", "subscription": summarize_subscription(result)}
    except ApiException as e:
        raise api_error(e)


def install_amq_streams_operator_data(
    namespace: str = "openshift-operators",
    channel: str = "stable",
    source: str = "redhat-operators",
    source_namespace: str = "openshift-marketplace",
    install_plan_approval: str = "Automatic",
) -> Dict[str, Any]:
    return install_olm_operator_data(
        namespace=namespace,
        package_name="amq-streams",
        channel=channel,
        source=source,
        source_namespace=source_namespace,
        install_plan_approval=install_plan_approval,
        subscription_name="amq-streams",
    )


def install_olm_operator_data(
    namespace: str = "openshift-operators",
    package_name: str = "",
    channel: str = "stable",
    source: str = "redhat-operators",
    source_namespace: str = "openshift-marketplace",
    install_plan_approval: str = "Automatic",
    subscription_name: Optional[str] = None,
    starting_csv: Optional[str] = None,
    create_operator_group: bool = False,
    operator_group_name: str = "mcp-operator-group",
    target_namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not package_name:
        raise HTTPException(status_code=400, detail="package_name is required")

    operator_group = None
    if create_operator_group:
        operator_group = create_operator_group_data(
            namespace=namespace,
            name=operator_group_name,
            target_namespaces=target_namespaces,
        )

    subscription = create_olm_subscription_data(
        namespace=namespace,
        package_name=package_name,
        channel=channel,
        source=source,
        source_namespace=source_namespace,
        install_plan_approval=install_plan_approval,
        name=subscription_name or package_name,
        starting_csv=starting_csv,
    )

    return {
        "status": "created",
        "operator_group": operator_group,
        "subscription": subscription["subscription"],
    }


def start_must_gather_data(
    namespace: str = "mcp-server",
    name: Optional[str] = None,
    image: Optional[str] = None,
    service_account_name: str = "mcp-openshift",
    timeout_seconds: int = 3600,
) -> Dict[str, Any]:
    validated_namespace = validated_dns_label(namespace, "namespace")
    job_name = validated_name(
        name or f"mcp-must-gather-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    gather_image = image or DEFAULT_MUST_GATHER_IMAGE
    command = [
        "/bin/bash",
        "-lc",
        (
            "set -o pipefail; "
            "mkdir -p /must-gather; cd /must-gather; "
            "if [ -x /usr/bin/gather ]; then /usr/bin/gather; "
            "elif command -v gather >/dev/null 2>&1; then gather; "
            "else echo 'No gather executable found in image' >&2; exit 127; fi"
        ),
    ]
    job = client.V1Job(
        metadata=client.V1ObjectMeta(
            name=job_name,
            namespace=validated_namespace,
            labels={
                "app.kubernetes.io/name": "mcp-must-gather",
                "app.kubernetes.io/part-of": "mcp-server",
            },
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=86400,
            active_deadline_seconds=timeout_seconds,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app.kubernetes.io/name": "mcp-must-gather",
                        "job-name": job_name,
                    }
                ),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    service_account_name=validated_name(service_account_name),
                    containers=[
                        client.V1Container(
                            name="must-gather",
                            image=gather_image,
                            image_pull_policy="IfNotPresent",
                            command=command,
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="must-gather-data", mount_path="/must-gather"
                                )
                            ],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="must-gather-data",
                            empty_dir=client.V1EmptyDirVolumeSource(),
                        )
                    ],
                ),
            ),
        ),
    )

    try:
        result = batch_v1.create_namespaced_job(validated_namespace, body=job)
        return {
            "status": "created",
            "job": summarize_job(result),
            "namespace": validated_namespace,
            "image": gather_image,
            "logs_tool": "get_must_gather_logs",
        }
    except ApiException as e:
        raise api_error(e)


def get_must_gather_logs_data(namespace: str, job_name: str) -> Dict[str, Any]:
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
            pod.metadata.name, validated_namespace, container="must-gather"
        )
        return {
            "job_name": job_name,
            "namespace": namespace,
            "pod_name": pod.metadata.name,
            "logs": logs,
        }
    except ApiException as e:
        raise api_error(e, "Must-gather pod not found")
