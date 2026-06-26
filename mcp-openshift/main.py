import contextlib
import inspect
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from pydantic import BaseModel, Field
from urllib3.exceptions import MaxRetryError, NewConnectionError

APP_VERSION = "0.3.1"

# --- OpenShift / KubeVirt API group constants ---
OPENSHIFT_ROUTE_GROUP = "route.openshift.io"
OPENSHIFT_ROUTE_VERSION = "v1"
OPENSHIFT_ROUTE_PLURAL = "routes"

OPENSHIFT_PROJECT_GROUP = "project.openshift.io"
OPENSHIFT_PROJECT_VERSION = "v1"
OPENSHIFT_PROJECT_PLURAL = "projects"

OPENSHIFT_APPS_GROUP = "apps.openshift.io"
OPENSHIFT_APPS_VERSION = "v1"

OPENSHIFT_BUILD_GROUP = "build.openshift.io"
OPENSHIFT_BUILD_VERSION = "v1"

OPENSHIFT_IMAGE_GROUP = "image.openshift.io"
OPENSHIFT_IMAGE_VERSION = "v1"

OPENSHIFT_USER_GROUP = "user.openshift.io"
OPENSHIFT_USER_VERSION = "v1"

OPENSHIFT_SECURITY_GROUP = "security.openshift.io"
OPENSHIFT_SECURITY_VERSION = "v1"

OPENSHIFT_CONFIG_GROUP = "config.openshift.io"
OPENSHIFT_CONFIG_VERSION = "v1"

MACHINE_GROUP = "machine.openshift.io"
MACHINE_VERSION = "v1beta1"

MACHINE_CONFIG_GROUP = "machineconfiguration.openshift.io"
MACHINE_CONFIG_VERSION = "v1"

OLM_GROUP = "operators.coreos.com"
OLM_VERSION = "v1alpha1"

KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
KUBEVIRT_VM_PLURAL = "virtualmachines"
KUBEVIRT_VMI_PLURAL = "virtualmachineinstances"

# --- Auth ---
AUTH_TOKEN_PLACEHOLDERS = {
    "replace-with-generated-token",
    "change-me",
    "changeme",
}
AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN")
if AUTH_TOKEN in AUTH_TOKEN_PLACEHOLDERS:
    raise RuntimeError("MCP_AUTH_TOKEN must be replaced with a generated secret token")

AUTH_PROTECTED_PREFIXES = (
    "/mcp",
    "/api/v1",
    "/namespaces",
    "/rbac",
    "/nodes",
    "/projects",
)

# --- Input validation ---
_SAFE_NAME_RE = re.compile(r"^[^\x00/\\]{1,253}$")


def validated_name(name: str) -> str:
    if not name or not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid resource name: {name!r}")
    return name


def csv_env(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def is_authorized_request(request: Request) -> bool:
    if not AUTH_TOKEN:
        return True
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and secrets.compare_digest(token, AUTH_TOKEN):
        return True
    api_key = request.headers.get("x-mcp-api-key", "")
    return bool(api_key) and secrets.compare_digest(api_key, AUTH_TOKEN)


# --- Pydantic models ---
class DeleteOptions(BaseModel):
    grace_period_seconds: Optional[int] = Field(default=None, ge=0)
    force: bool = False


class ResourceRequirementsPatch(BaseModel):
    limits: Optional[Dict[str, str]] = None
    requests: Optional[Dict[str, str]] = None


class LogQuery(BaseModel):
    container: Optional[str] = None
    tail_lines: int = Field(default=200, ge=1, le=10000)
    since_seconds: Optional[int] = Field(default=None, ge=1)
    previous: bool = False


class ScaleRequest(BaseModel):
    replicas: int = Field(ge=0, le=500)


# --- Kubernetes client setup ---
def configure_kubernetes() -> bool:
    try:
        config.load_incluster_config()
        return True
    except config.ConfigException:
        try:
            config.load_kube_config()
            return True
        except config.ConfigException:
            return False


K8S_AVAILABLE = configure_kubernetes()
if not K8S_AVAILABLE:
    import logging as _logging

    _logging.warning(
        "Could not configure Kubernetes client - API calls will fail until a valid "
        "kubeconfig or in-cluster config is available"
    )

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
batch_v1 = client.BatchV1Api()
rbac_v1 = client.RbacAuthorizationV1Api()
networking_v1 = client.NetworkingV1Api()
autoscaling_v2 = client.AutoscalingV2Api()
storage_v1 = client.StorageV1Api()
custom_objects = client.CustomObjectsApi()


# --- Error helpers ---
def api_error(
    error: ApiException, not_found_detail: str = "Resource not found"
) -> HTTPException:
    if error.status == 404:
        return HTTPException(status_code=404, detail=not_found_detail)
    if error.status == 403:
        return HTTPException(status_code=403, detail="Forbidden by Kubernetes RBAC")
    if error.status == 401:
        return HTTPException(status_code=401, detail="Kubernetes authentication failed")
    return HTTPException(status_code=500, detail="Internal server error")


def crd_not_available(resource_type: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"{resource_type} API not available on this cluster (CRD not installed)",
    )


def list_response(items: List[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    return {"kind": kind, "count": len(items), "items": items}


# --- Summarizers: Kubernetes core ---
def object_metadata(obj: Any) -> Dict[str, Any]:
    return {
        "name": obj.metadata.name,
        "namespace": obj.metadata.namespace,
        "uid": obj.metadata.uid,
        "resource_version": obj.metadata.resource_version,
        "labels": obj.metadata.labels or {},
        "annotations": obj.metadata.annotations or {},
        "created_at": (
            obj.metadata.creation_timestamp.isoformat()
            if obj.metadata.creation_timestamp
            else None
        ),
    }


def container_resources(container: Any) -> Dict[str, Any]:
    resources = container.resources
    if not resources:
        return {"limits": {}, "requests": {}}
    return {"limits": resources.limits or {}, "requests": resources.requests or {}}


def summarize_container(container: Any, status: Optional[Any] = None) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "name": container.name,
        "image": container.image,
        "image_pull_policy": container.image_pull_policy,
        "resources": container_resources(container),
        "ports": [port.to_dict() for port in (container.ports or [])],
    }
    if status:
        data.update(
            {
                "ready": status.ready,
                "started": status.started,
                "restart_count": status.restart_count,
                "image_id": status.image_id,
                "container_id": status.container_id,
                "state": status.state.to_dict() if status.state else None,
                "last_state": (
                    status.last_state.to_dict() if status.last_state else None
                ),
            }
        )
    return data


def summarize_namespace(namespace: Any) -> Dict[str, Any]:
    return {
        **object_metadata(namespace),
        "status": namespace.status.phase,
        "conditions": [c.to_dict() for c in (namespace.status.conditions or [])],
    }


def summarize_node(node: Any) -> Dict[str, Any]:
    labels = node.metadata.labels or {}
    roles = [
        k.split("/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/")
    ] or ["worker"]
    ni = node.status.node_info
    conditions = {c.type: c.status for c in (node.status.conditions or [])}
    return {
        **object_metadata(node),
        "roles": roles,
        "ready": conditions.get("Ready") == "True",
        "unschedulable": node.spec.unschedulable or False,
        "addresses": [a.to_dict() for a in (node.status.addresses or [])],
        "capacity": node.status.capacity or {},
        "allocatable": node.status.allocatable or {},
        "architecture": ni.architecture if ni else None,
        "os_image": ni.os_image if ni else None,
        "kernel_version": ni.kernel_version if ni else None,
        "container_runtime": ni.container_runtime_version if ni else None,
        "kubelet_version": ni.kubelet_version if ni else None,
        "conditions": [c.to_dict() for c in (node.status.conditions or [])],
        "taints": [t.to_dict() for t in (node.spec.taints or [])],
    }


def summarize_pod(pod: Any) -> Dict[str, Any]:
    statuses = {s.name: s for s in (pod.status.container_statuses or [])}
    return {
        **object_metadata(pod),
        "phase": pod.status.phase,
        "pod_ip": pod.status.pod_ip,
        "host_ip": pod.status.host_ip,
        "node_name": pod.spec.node_name,
        "qos_class": pod.status.qos_class,
        "restart_policy": pod.spec.restart_policy,
        "service_account": pod.spec.service_account_name,
        "containers": [
            summarize_container(c, statuses.get(c.name))
            for c in (pod.spec.containers or [])
        ],
        "init_containers": [
            summarize_container(c) for c in (pod.spec.init_containers or [])
        ],
        "conditions": [c.to_dict() for c in (pod.status.conditions or [])],
    }


def summarize_persistent_volume(pv: Any) -> Dict[str, Any]:
    return {
        **object_metadata(pv),
        "capacity": pv.spec.capacity or {},
        "access_modes": pv.spec.access_modes or [],
        "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
        "storage_class": pv.spec.storage_class_name,
        "volume_mode": pv.spec.volume_mode,
        "status": pv.status.phase,
        "claim_ref": pv.spec.claim_ref.to_dict() if pv.spec.claim_ref else None,
    }


def summarize_pvc(pvc: Any) -> Dict[str, Any]:
    requested = None
    if pvc.spec.resources and pvc.spec.resources.requests:
        requested = pvc.spec.resources.requests.get("storage")
    return {
        **object_metadata(pvc),
        "status": pvc.status.phase,
        "capacity": pvc.status.capacity or {},
        "access_modes": pvc.status.access_modes or [],
        "storage_class": pvc.spec.storage_class_name,
        "volume_mode": pvc.spec.volume_mode,
        "volume_name": pvc.spec.volume_name,
        "requested_storage": requested,
    }


def summarize_storage_class(sc: Any) -> Dict[str, Any]:
    return {
        **object_metadata(sc),
        "provisioner": sc.provisioner,
        "reclaim_policy": sc.reclaim_policy,
        "volume_binding_mode": sc.volume_binding_mode,
        "allow_volume_expansion": sc.allow_volume_expansion,
        "parameters": sc.parameters or {},
    }


def summarize_config_map(cm: Any) -> Dict[str, Any]:
    return {
        **object_metadata(cm),
        "data": cm.data or {},
        "binary_data_keys": list(cm.binary_data.keys()) if cm.binary_data else [],
    }


def summarize_service_account(sa: Any) -> Dict[str, Any]:
    return {
        **object_metadata(sa),
        "secrets": [s.to_dict() for s in (sa.secrets or [])],
        "image_pull_secrets": [s.to_dict() for s in (sa.image_pull_secrets or [])],
        "automount_service_account_token": sa.automount_service_account_token,
    }


def summarize_resource_quota(rq: Any) -> Dict[str, Any]:
    return {
        **object_metadata(rq),
        "hard": rq.spec.hard or {},
        "used": rq.status.used or {},
        "scopes": rq.spec.scopes or [],
    }


def summarize_limit_range(lr: Any) -> Dict[str, Any]:
    return {
        **object_metadata(lr),
        "limits": [lim.to_dict() for lim in (lr.spec.limits or [])],
    }


def summarize_deployment(deployment: Any) -> Dict[str, Any]:
    desired = deployment.spec.replicas or 0
    updated = deployment.status.updated_replicas or 0
    available = deployment.status.available_replicas or 0
    observed = deployment.status.observed_generation or 0
    generation = deployment.metadata.generation or 0
    return {
        **object_metadata(deployment),
        "replicas": desired,
        "ready_replicas": deployment.status.ready_replicas or 0,
        "available_replicas": available,
        "updated_replicas": updated,
        "rollout_complete": observed >= generation
        and updated == desired
        and available == desired,
        "observed_generation": observed,
        "generation": generation,
        "strategy": (
            deployment.spec.strategy.to_dict() if deployment.spec.strategy else None
        ),
        "containers": [
            summarize_container(c)
            for c in (deployment.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (deployment.status.conditions or [])],
    }


def summarize_statefulset(ss: Any) -> Dict[str, Any]:
    return {
        **object_metadata(ss),
        "replicas": ss.spec.replicas or 0,
        "ready_replicas": ss.status.ready_replicas or 0,
        "current_replicas": ss.status.current_replicas or 0,
        "updated_replicas": ss.status.updated_replicas or 0,
        "service_name": ss.spec.service_name,
        "update_strategy": (
            ss.spec.update_strategy.to_dict() if ss.spec.update_strategy else None
        ),
        "containers": [
            summarize_container(c) for c in (ss.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (ss.status.conditions or [])],
    }


def summarize_daemonset(ds: Any) -> Dict[str, Any]:
    return {
        **object_metadata(ds),
        "desired_number_scheduled": ds.status.desired_number_scheduled or 0,
        "number_ready": ds.status.number_ready or 0,
        "number_available": ds.status.number_available or 0,
        "number_unavailable": ds.status.number_unavailable or 0,
        "updated_number_scheduled": ds.status.updated_number_scheduled or 0,
        "update_strategy": (
            ds.spec.update_strategy.to_dict() if ds.spec.update_strategy else None
        ),
        "containers": [
            summarize_container(c) for c in (ds.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (ds.status.conditions or [])],
    }


def summarize_replicaset(rs: Any) -> Dict[str, Any]:
    return {
        **object_metadata(rs),
        "replicas": rs.spec.replicas or 0,
        "ready_replicas": rs.status.ready_replicas or 0,
        "available_replicas": rs.status.available_replicas or 0,
        "owner_references": [r.to_dict() for r in (rs.metadata.owner_references or [])],
        "containers": [
            summarize_container(c) for c in (rs.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (rs.status.conditions or [])],
    }


def summarize_hpa(hpa: Any) -> Dict[str, Any]:
    return {
        **object_metadata(hpa),
        "min_replicas": hpa.spec.min_replicas,
        "max_replicas": hpa.spec.max_replicas,
        "current_replicas": hpa.status.current_replicas or 0,
        "desired_replicas": hpa.status.desired_replicas or 0,
        "scale_target_ref": (
            hpa.spec.scale_target_ref.to_dict() if hpa.spec.scale_target_ref else None
        ),
        "metrics": [m.to_dict() for m in (hpa.spec.metrics or [])],
        "current_metrics": [m.to_dict() for m in (hpa.status.current_metrics or [])],
        "conditions": [c.to_dict() for c in (hpa.status.conditions or [])],
    }


def summarize_ingress(ingress: Any) -> Dict[str, Any]:
    lb = None
    if ingress.status and ingress.status.load_balancer:
        lb = ingress.status.load_balancer.to_dict()
    return {
        **object_metadata(ingress),
        "ingress_class_name": ingress.spec.ingress_class_name,
        "rules": [r.to_dict() for r in (ingress.spec.rules or [])],
        "tls": [t.to_dict() for t in (ingress.spec.tls or [])],
        "load_balancer": lb,
    }


def summarize_network_policy(np: Any) -> Dict[str, Any]:
    return {
        **object_metadata(np),
        "pod_selector": (
            np.spec.pod_selector.to_dict() if np.spec.pod_selector else None
        ),
        "ingress": [r.to_dict() for r in (np.spec.ingress or [])],
        "egress": [r.to_dict() for r in (np.spec.egress or [])],
        "policy_types": np.spec.policy_types or [],
    }


def summarize_job(job: Any) -> Dict[str, Any]:
    return {
        **object_metadata(job),
        "parallelism": job.spec.parallelism,
        "completions": job.spec.completions,
        "active": job.status.active or 0,
        "succeeded": job.status.succeeded or 0,
        "failed": job.status.failed or 0,
        "start_time": (
            job.status.start_time.isoformat() if job.status.start_time else None
        ),
        "completion_time": (
            job.status.completion_time.isoformat()
            if job.status.completion_time
            else None
        ),
        "conditions": [c.to_dict() for c in (job.status.conditions or [])],
    }


def summarize_cronjob(cronjob: Any) -> Dict[str, Any]:
    return {
        **object_metadata(cronjob),
        "schedule": cronjob.spec.schedule,
        "suspend": cronjob.spec.suspend,
        "active_jobs": [
            {"name": ref.name, "namespace": ref.namespace}
            for ref in (cronjob.status.active or [])
        ],
        "last_schedule_time": (
            cronjob.status.last_schedule_time.isoformat()
            if cronjob.status.last_schedule_time
            else None
        ),
        "last_successful_time": (
            cronjob.status.last_successful_time.isoformat()
            if cronjob.status.last_successful_time
            else None
        ),
    }


def summarize_service(service: Any) -> Dict[str, Any]:
    return {
        **object_metadata(service),
        "type": service.spec.type,
        "cluster_ip": service.spec.cluster_ip,
        "external_ips": service.spec.external_i_ps or [],
        "ports": [p.to_dict() for p in (service.spec.ports or [])],
        "selector": service.spec.selector or {},
    }


def summarize_event(event: Any) -> Dict[str, Any]:
    event_time = event.event_time or event.last_timestamp or event.first_timestamp
    return {
        **object_metadata(event),
        "type": event.type,
        "reason": event.reason,
        "message": event.message,
        "count": event.count,
        "involved_object": (
            event.involved_object.to_dict() if event.involved_object else None
        ),
        "event_time": event_time.isoformat() if event_time else None,
    }


def summarize_role(role: Any) -> Dict[str, Any]:
    return {
        **object_metadata(role),
        "rules": [r.to_dict() for r in (role.rules or [])],
    }


def summarize_binding(binding: Any) -> Dict[str, Any]:
    return {
        **object_metadata(binding),
        "role_ref": binding.role_ref.to_dict() if binding.role_ref else None,
        "subjects": [s.to_dict() for s in (binding.subjects or [])],
    }


# --- Summarizers: OpenShift custom resources (dicts from CustomObjectsApi) ---
def _meta(obj: Dict[str, Any]) -> Dict[str, Any]:
    m = obj.get("metadata", {})
    return {
        "name": m.get("name"),
        "namespace": m.get("namespace"),
        "uid": m.get("uid"),
        "labels": m.get("labels", {}),
        "annotations": m.get("annotations", {}),
        "created_at": m.get("creationTimestamp"),
    }


def summarize_route(route: Dict[str, Any]) -> Dict[str, Any]:
    spec = route.get("spec", {})
    status = route.get("status", {})
    return {
        **_meta(route),
        "host": spec.get("host"),
        "path": spec.get("path"),
        "to": spec.get("to"),
        "port": spec.get("port"),
        "tls": spec.get("tls"),
        "ingress": status.get("ingress", []),
    }


def summarize_project(proj: Dict[str, Any]) -> Dict[str, Any]:
    annotations = proj.get("metadata", {}).get("annotations", {})
    return {
        **_meta(proj),
        "status": proj.get("status", {}).get("phase"),
        "display_name": annotations.get("openshift.io/display-name", ""),
        "description": annotations.get("openshift.io/description", ""),
    }


def summarize_deployment_config(dc: Dict[str, Any]) -> Dict[str, Any]:
    spec = dc.get("spec", {})
    status = dc.get("status", {})
    containers = spec.get("template", {}).get("spec", {}).get("containers", [])
    return {
        **_meta(dc),
        "replicas": spec.get("replicas", 0),
        "ready_replicas": status.get("readyReplicas", 0),
        "available_replicas": status.get("availableReplicas", 0),
        "updated_replicas": status.get("updatedReplicas", 0),
        "latest_version": status.get("latestVersion"),
        "observed_generation": status.get("observedGeneration"),
        "strategy": spec.get("strategy", {}).get("type"),
        "containers": [
            {
                "name": c.get("name"),
                "image": c.get("image"),
                "resources": c.get("resources", {}),
            }
            for c in containers
        ],
        "triggers": [t.get("type") for t in spec.get("triggers", [])],
        "conditions": status.get("conditions", []),
    }


def summarize_build_config(bc: Dict[str, Any]) -> Dict[str, Any]:
    spec = bc.get("spec", {})
    return {
        **_meta(bc),
        "source_type": spec.get("source", {}).get("type"),
        "source_git": spec.get("source", {}).get("git", {}).get("uri"),
        "source_ref": spec.get("source", {}).get("git", {}).get("ref"),
        "output_to": spec.get("output", {}).get("to"),
        "strategy": spec.get("strategy", {}).get("type"),
        "last_version": bc.get("status", {}).get("lastVersion"),
        "triggers": [t.get("type") for t in spec.get("triggers", [])],
    }


def summarize_build(build: Dict[str, Any]) -> Dict[str, Any]:
    spec = build.get("spec", {})
    status = build.get("status", {})
    return {
        **_meta(build),
        "phase": status.get("phase"),
        "reason": status.get("reason"),
        "message": status.get("message"),
        "start_timestamp": status.get("startTimestamp"),
        "completion_timestamp": status.get("completionTimestamp"),
        "duration": status.get("duration"),
        "output_docker_image": status.get("outputDockerImageReference"),
        "strategy": spec.get("strategy", {}).get("type"),
    }


def summarize_image_stream(is_obj: Dict[str, Any]) -> Dict[str, Any]:
    status = is_obj.get("status", {})
    spec = is_obj.get("spec", {})
    return {
        **_meta(is_obj),
        "docker_image_repository": status.get("dockerImageRepository"),
        "public_docker_image_repository": status.get("publicDockerImageRepository"),
        "lookup_policy_local": spec.get("lookupPolicy", {}).get("local", False),
        "tags": [
            {
                "tag": t.get("tag"),
                "items": [
                    {
                        "created": item.get("created"),
                        "docker_image_reference": item.get("dockerImageReference"),
                        "image": item.get("image"),
                    }
                    for item in t.get("items", [])[:3]
                ],
            }
            for t in status.get("tags", [])
        ],
    }


def summarize_scc(scc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_meta(scc),
        "allow_privileged": scc.get("allowPrivilegedContainer", False),
        "allow_privilege_escalation": scc.get("allowPrivilegeEscalation"),
        "run_as_user": scc.get("runAsUser", {}),
        "se_linux_context": scc.get("seLinuxContext", {}),
        "fs_group": scc.get("fsGroup", {}),
        "supplemental_groups": scc.get("supplementalGroups", {}),
        "volumes": scc.get("volumes", []),
        "users": scc.get("users", []),
        "groups": scc.get("groups", []),
        "priority": scc.get("priority"),
    }


def summarize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_meta(user),
        "full_name": user.get("fullName", ""),
        "identities": user.get("identities", []),
        "groups": user.get("groups", []),
    }


def summarize_group(group: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_meta(group),
        "users": group.get("users", []),
    }


def summarize_cluster_version(cv: Dict[str, Any]) -> Dict[str, Any]:
    spec = cv.get("spec", {})
    status = cv.get("status", {})
    history = status.get("history", [])
    current = next(
        (h for h in history if h.get("state") == "Completed"),
        history[0] if history else {},
    )
    desired_update = spec.get("desiredUpdate")
    return {
        **_meta(cv),
        "cluster_id": spec.get("clusterID"),
        "channel": spec.get("channel"),
        "version": current.get("version"),
        "state": current.get("state"),
        "verified": current.get("verified"),
        "started_time": current.get("startedTime"),
        "completion_time": current.get("completionTime"),
        "desired_update": desired_update,
        "available_updates": [
            u.get("version") for u in status.get("availableUpdates", [])
        ],
        "conditions": status.get("conditions", []),
    }


def summarize_cluster_operator(co: Dict[str, Any]) -> Dict[str, Any]:
    status = co.get("status", {})
    conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
    operator_version = next(
        (
            v.get("version")
            for v in status.get("versions", [])
            if v.get("name") == "operator"
        ),
        None,
    )
    return {
        **_meta(co),
        "available": conditions.get("Available") == "True",
        "progressing": conditions.get("Progressing") == "True",
        "degraded": conditions.get("Degraded") == "True",
        "version": operator_version,
        "related_objects": status.get("relatedObjects", []),
        "conditions": status.get("conditions", []),
    }


def summarize_machine_config_pool(mcp_obj: Dict[str, Any]) -> Dict[str, Any]:
    spec = mcp_obj.get("spec", {})
    status = mcp_obj.get("status", {})
    conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
    return {
        **_meta(mcp_obj),
        "paused": spec.get("paused", False),
        "machine_count": status.get("machineCount", 0),
        "ready_machine_count": status.get("readyMachineCount", 0),
        "updated_machine_count": status.get("updatedMachineCount", 0),
        "unavailable_machine_count": status.get("unavailableMachineCount", 0),
        "degraded_machine_count": status.get("degradedMachineCount", 0),
        "updated": conditions.get("Updated") == "True",
        "updating": conditions.get("Updating") == "True",
        "degraded": conditions.get("Degraded") == "True",
        "configuration": status.get("configuration", {}).get("name"),
        "conditions": status.get("conditions", []),
    }


def summarize_machine(machine: Dict[str, Any]) -> Dict[str, Any]:
    spec = machine.get("spec", {})
    status = machine.get("status", {})
    conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
    return {
        **_meta(machine),
        "phase": status.get("phase"),
        "node_ref": (
            status.get("nodeRef", {}).get("name") if status.get("nodeRef") else None
        ),
        "provider_id": spec.get("providerID"),
        "ready": conditions.get("Ready") == "True",
        "conditions": status.get("conditions", []),
    }


def summarize_machine_set(ms: Dict[str, Any]) -> Dict[str, Any]:
    spec = ms.get("spec", {})
    status = ms.get("status", {})
    return {
        **_meta(ms),
        "replicas": spec.get("replicas", 0),
        "ready_replicas": status.get("readyReplicas", 0),
        "available_replicas": status.get("availableReplicas", 0),
        "fully_labeled_replicas": status.get("fullyLabeledReplicas", 0),
        "error_reason": status.get("errorReason"),
        "error_message": status.get("errorMessage"),
    }


def summarize_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    spec = sub.get("spec", {})
    status = sub.get("status", {})
    return {
        **_meta(sub),
        "package": spec.get("name"),
        "channel": spec.get("channel"),
        "source": spec.get("source"),
        "source_namespace": spec.get("sourceNamespace"),
        "install_plan_approval": spec.get("installPlanApproval"),
        "current_csv": status.get("currentCSV"),
        "installed_csv": status.get("installedCSV"),
        "state": status.get("state"),
        "conditions": status.get("conditions", []),
    }


def summarize_csv(csv_obj: Dict[str, Any]) -> Dict[str, Any]:
    spec = csv_obj.get("spec", {})
    status = csv_obj.get("status", {})
    return {
        **_meta(csv_obj),
        "display_name": spec.get("displayName"),
        "version": spec.get("version"),
        "maturity": spec.get("maturity"),
        "phase": status.get("phase"),
        "reason": status.get("reason"),
        "conditions": [
            {
                "type": c.get("type"),
                "status": c.get("status"),
                "message": (c.get("message") or "")[:200],
            }
            for c in status.get("conditions", [])
        ],
    }


def summarize_catalog_source(cs: Dict[str, Any]) -> Dict[str, Any]:
    spec = cs.get("spec", {})
    status = cs.get("status", {})
    poll_interval = None
    if spec.get("updateStrategy", {}).get("registryPoll"):
        poll_interval = spec["updateStrategy"]["registryPoll"].get("interval")
    return {
        **_meta(cs),
        "source_type": spec.get("sourceType"),
        "image": spec.get("image"),
        "display_name": spec.get("displayName"),
        "publisher": spec.get("publisher"),
        "registry_poll_interval": poll_interval,
        "last_observed_state": status.get("connectionState", {}).get(
            "lastObservedState"
        ),
    }


def summarize_virtualmachine(vm: Dict[str, Any]) -> Dict[str, Any]:
    spec = vm.get("spec", {})
    status = vm.get("status", {})
    return {
        **_meta(vm),
        "running": spec.get("running"),
        "phase": status.get("printableStatus"),
        "ready": status.get("ready", False),
        "created": status.get("created", False),
        "volume_snapshot_statuses": status.get("volumeSnapshotStatuses", []),
        "state_change_requests": status.get("stateChangeRequests", []),
    }


def summarize_vmi(vmi: Dict[str, Any]) -> Dict[str, Any]:
    status = vmi.get("status", {})
    interfaces = status.get("interfaces", [])
    return {
        **_meta(vmi),
        "phase": status.get("phase"),
        "node_name": status.get("nodeName"),
        "ip_address": interfaces[0].get("ipAddress") if interfaces else None,
        "ip_addresses": [i.get("ipAddress") for i in interfaces if i.get("ipAddress")],
        "guest_os": status.get("guestOSInfo", {}).get("name"),
        "ready": any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in status.get("conditions", [])
        ),
        "live_migratable": any(
            c.get("type") == "LiveMigratable" and c.get("status") == "True"
            for c in status.get("conditions", [])
        ),
        "conditions": status.get("conditions", []),
    }


# ============================================================
# Data functions — Kubernetes core
# ============================================================
def list_namespaces_data() -> Dict[str, Any]:
    try:
        ns = core_v1.list_namespace()
        return list_response(
            [summarize_namespace(n) for n in ns.items], "NamespaceList"
        )
    except ApiException as e:
        raise api_error(e)


def get_namespace_data(namespace: str) -> Dict[str, Any]:
    try:
        return summarize_namespace(core_v1.read_namespace(validated_name(namespace)))
    except ApiException as e:
        raise api_error(e, "Namespace not found")


def list_nodes_data(label_selector: Optional[str] = None) -> Dict[str, Any]:
    try:
        nodes = core_v1.list_node(label_selector=label_selector)
        return list_response([summarize_node(n) for n in nodes.items], "NodeList")
    except ApiException as e:
        raise api_error(e)


def get_node_data(node_name: str) -> Dict[str, Any]:
    try:
        return summarize_node(core_v1.read_node(validated_name(node_name)))
    except ApiException as e:
        raise api_error(e, "Node not found")


def list_pods_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    try:
        pods = core_v1.list_namespaced_pod(
            validated_name(namespace), label_selector=label_selector
        )
        return list_response([summarize_pod(p) for p in pods.items], "PodList")
    except ApiException as e:
        raise api_error(e)


def get_pod_data(namespace: str, pod_name: str) -> Dict[str, Any]:
    try:
        return summarize_pod(
            core_v1.read_namespaced_pod(
                validated_name(pod_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Pod not found")


def delete_pod_data(
    namespace: str, pod_name: str, options: Optional[DeleteOptions] = None
) -> Dict[str, Any]:
    try:
        options = options or DeleteOptions()
        grace_period = 0 if options.force else options.grace_period_seconds
        body = client.V1DeleteOptions(grace_period_seconds=grace_period)
        result = core_v1.delete_namespaced_pod(
            validated_name(pod_name), validated_name(namespace), body=body
        )
        return {
            "status": "delete_requested",
            "name": pod_name,
            "namespace": namespace,
            "force": options.force,
            "grace_period_seconds": grace_period,
            "result": result.to_dict() if hasattr(result, "to_dict") else result,
        }
    except ApiException as e:
        raise api_error(e, "Pod not found")


def get_pod_logs_data(
    namespace: str, pod_name: str, query: Optional[LogQuery] = None
) -> Dict[str, Any]:
    try:
        query = query or LogQuery()
        logs = core_v1.read_namespaced_pod_log(
            name=validated_name(pod_name),
            namespace=validated_name(namespace),
            container=query.container,
            tail_lines=query.tail_lines,
            since_seconds=query.since_seconds,
            previous=query.previous,
        )
        return {
            "namespace": namespace,
            "pod": pod_name,
            "container": query.container,
            "tail_lines": query.tail_lines,
            "since_seconds": query.since_seconds,
            "previous": query.previous,
            "logs": logs,
        }
    except ApiException as e:
        raise api_error(e, "Pod logs not found")


def list_events_data(
    namespace: str,
    involved_object_name: Optional[str] = None,
    involved_object_kind: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        selectors = []
        if involved_object_name:
            selectors.append(f"involvedObject.name={involved_object_name}")
        if involved_object_kind:
            selectors.append(f"involvedObject.kind={involved_object_kind}")
        events = core_v1.list_namespaced_event(
            validated_name(namespace), field_selector=",".join(selectors) or None
        )
        return list_response([summarize_event(e) for e in events.items], "EventList")
    except ApiException as e:
        raise api_error(e)


def list_containers_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    pods = list_pods_data(namespace, label_selector=label_selector)["items"]
    containers = []
    for pod in pods:
        for container in pod["containers"]:
            containers.append(
                {
                    "namespace": namespace,
                    "pod": pod["name"],
                    "pod_phase": pod["phase"],
                    **container,
                }
            )
    return list_response(containers, "ContainerList")


def list_services_data(namespace: str) -> Dict[str, Any]:
    try:
        svcs = core_v1.list_namespaced_service(validated_name(namespace))
        return list_response([summarize_service(s) for s in svcs.items], "ServiceList")
    except ApiException as e:
        raise api_error(e)


def get_service_data(namespace: str, service_name: str) -> Dict[str, Any]:
    try:
        return summarize_service(
            core_v1.read_namespaced_service(
                validated_name(service_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Service not found")


def list_persistent_volumes_data() -> Dict[str, Any]:
    try:
        pvs = core_v1.list_persistent_volume()
        return list_response(
            [summarize_persistent_volume(p) for p in pvs.items], "PersistentVolumeList"
        )
    except ApiException as e:
        raise api_error(e)


def get_persistent_volume_data(pv_name: str) -> Dict[str, Any]:
    try:
        return summarize_persistent_volume(
            core_v1.read_persistent_volume(validated_name(pv_name))
        )
    except ApiException as e:
        raise api_error(e, "PersistentVolume not found")


def list_storage_classes_data() -> Dict[str, Any]:
    try:
        scs = storage_v1.list_storage_class()
        return list_response(
            [summarize_storage_class(s) for s in scs.items], "StorageClassList"
        )
    except ApiException as e:
        raise api_error(e)


def list_pvcs_data(namespace: str) -> Dict[str, Any]:
    try:
        pvcs = core_v1.list_namespaced_persistent_volume_claim(
            validated_name(namespace)
        )
        return list_response(
            [summarize_pvc(p) for p in pvcs.items], "PersistentVolumeClaimList"
        )
    except ApiException as e:
        raise api_error(e)


def get_pvc_data(namespace: str, pvc_name: str) -> Dict[str, Any]:
    try:
        return summarize_pvc(
            core_v1.read_namespaced_persistent_volume_claim(
                validated_name(pvc_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "PersistentVolumeClaim not found")


def list_config_maps_data(namespace: str) -> Dict[str, Any]:
    try:
        cms = core_v1.list_namespaced_config_map(validated_name(namespace))
        return list_response(
            [summarize_config_map(c) for c in cms.items], "ConfigMapList"
        )
    except ApiException as e:
        raise api_error(e)


def get_config_map_data(namespace: str, cm_name: str) -> Dict[str, Any]:
    try:
        return summarize_config_map(
            core_v1.read_namespaced_config_map(
                validated_name(cm_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "ConfigMap not found")


def list_service_accounts_data(namespace: str) -> Dict[str, Any]:
    try:
        sas = core_v1.list_namespaced_service_account(validated_name(namespace))
        return list_response(
            [summarize_service_account(s) for s in sas.items], "ServiceAccountList"
        )
    except ApiException as e:
        raise api_error(e)


def get_service_account_data(namespace: str, sa_name: str) -> Dict[str, Any]:
    try:
        return summarize_service_account(
            core_v1.read_namespaced_service_account(
                validated_name(sa_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "ServiceAccount not found")


def list_resource_quotas_data(namespace: str) -> Dict[str, Any]:
    try:
        rqs = core_v1.list_namespaced_resource_quota(validated_name(namespace))
        return list_response(
            [summarize_resource_quota(r) for r in rqs.items], "ResourceQuotaList"
        )
    except ApiException as e:
        raise api_error(e)


def get_resource_quota_data(namespace: str, rq_name: str) -> Dict[str, Any]:
    try:
        return summarize_resource_quota(
            core_v1.read_namespaced_resource_quota(
                validated_name(rq_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "ResourceQuota not found")


def list_limit_ranges_data(namespace: str) -> Dict[str, Any]:
    try:
        lrs = core_v1.list_namespaced_limit_range(validated_name(namespace))
        return list_response(
            [summarize_limit_range(r) for r in lrs.items], "LimitRangeList"
        )
    except ApiException as e:
        raise api_error(e)


# ============================================================
# Data functions — Kubernetes apps
# ============================================================
def list_deployments_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    try:
        deps = apps_v1.list_namespaced_deployment(
            validated_name(namespace), label_selector=label_selector
        )
        return list_response(
            [summarize_deployment(d) for d in deps.items], "DeploymentList"
        )
    except ApiException as e:
        raise api_error(e)


def get_deployment_data(namespace: str, deployment_name: str) -> Dict[str, Any]:
    try:
        return summarize_deployment(
            apps_v1.read_namespaced_deployment(
                validated_name(deployment_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Deployment not found")


def rollout_restart_deployment_data(
    namespace: str, deployment_name: str
) -> Dict[str, Any]:
    try:
        restarted_at = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": restarted_at
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(
            validated_name(deployment_name), validated_name(namespace), body
        )
        return {
            "status": "rollout_restart_requested",
            "name": deployment_name,
            "namespace": namespace,
            "restarted_at": restarted_at,
        }
    except ApiException as e:
        raise api_error(e, "Deployment not found")


def scale_deployment_data(
    namespace: str, deployment_name: str, replicas: int
) -> Dict[str, Any]:
    try:
        apps_v1.patch_namespaced_deployment(
            validated_name(deployment_name),
            validated_name(namespace),
            {"spec": {"replicas": replicas}},
        )
        return {
            "status": "scale_requested",
            "name": deployment_name,
            "namespace": namespace,
            "replicas": replicas,
        }
    except ApiException as e:
        raise api_error(e, "Deployment not found")


def update_deployment_container_resources_data(
    namespace: str,
    deployment_name: str,
    container_name: str,
    resources: ResourceRequirementsPatch,
) -> Dict[str, Any]:
    try:
        deployment = apps_v1.read_namespaced_deployment(
            validated_name(deployment_name), validated_name(namespace)
        )
        containers = deployment.spec.template.spec.containers or []
        if not any(c.name == container_name for c in containers):
            raise HTTPException(
                status_code=404, detail="Container not found in deployment"
            )
        patch_resources: Dict[str, Any] = {}
        if resources.limits is not None:
            patch_resources["limits"] = resources.limits
        if resources.requests is not None:
            patch_resources["requests"] = resources.requests
        if not patch_resources:
            raise HTTPException(
                status_code=400,
                detail="At least one of limits or requests must be provided",
            )
        body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {"name": container_name, "resources": patch_resources}
                        ]
                    }
                }
            }
        }
        updated = apps_v1.patch_namespaced_deployment(
            validated_name(deployment_name), validated_name(namespace), body
        )
        matching = next(
            c for c in updated.spec.template.spec.containers if c.name == container_name
        )
        return {
            "status": "resources_updated",
            "deployment": deployment_name,
            "namespace": namespace,
            "container": summarize_container(matching),
        }
    except ApiException as e:
        raise api_error(e, "Deployment not found")


def list_statefulsets_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    try:
        ssets = apps_v1.list_namespaced_stateful_set(
            validated_name(namespace), label_selector=label_selector
        )
        return list_response(
            [summarize_statefulset(s) for s in ssets.items], "StatefulSetList"
        )
    except ApiException as e:
        raise api_error(e)


def get_statefulset_data(namespace: str, name: str) -> Dict[str, Any]:
    try:
        return summarize_statefulset(
            apps_v1.read_namespaced_stateful_set(
                validated_name(name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "StatefulSet not found")


def rollout_restart_statefulset_data(namespace: str, name: str) -> Dict[str, Any]:
    try:
        restarted_at = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": restarted_at
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_stateful_set(
            validated_name(name), validated_name(namespace), body
        )
        return {
            "status": "rollout_restart_requested",
            "name": name,
            "namespace": namespace,
            "restarted_at": restarted_at,
        }
    except ApiException as e:
        raise api_error(e, "StatefulSet not found")


def scale_statefulset_data(namespace: str, name: str, replicas: int) -> Dict[str, Any]:
    try:
        apps_v1.patch_namespaced_stateful_set(
            validated_name(name),
            validated_name(namespace),
            {"spec": {"replicas": replicas}},
        )
        return {
            "status": "scale_requested",
            "name": name,
            "namespace": namespace,
            "replicas": replicas,
        }
    except ApiException as e:
        raise api_error(e, "StatefulSet not found")


def list_daemonsets_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    try:
        dsets = apps_v1.list_namespaced_daemon_set(
            validated_name(namespace), label_selector=label_selector
        )
        return list_response(
            [summarize_daemonset(d) for d in dsets.items], "DaemonSetList"
        )
    except ApiException as e:
        raise api_error(e)


def get_daemonset_data(namespace: str, name: str) -> Dict[str, Any]:
    try:
        return summarize_daemonset(
            apps_v1.read_namespaced_daemon_set(
                validated_name(name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "DaemonSet not found")


def list_replicasets_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    try:
        rsets = apps_v1.list_namespaced_replica_set(
            validated_name(namespace), label_selector=label_selector
        )
        return list_response(
            [summarize_replicaset(r) for r in rsets.items], "ReplicaSetList"
        )
    except ApiException as e:
        raise api_error(e)


def list_hpas_data(namespace: str) -> Dict[str, Any]:
    try:
        hpas = autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(
            validated_name(namespace)
        )
        return list_response(
            [summarize_hpa(h) for h in hpas.items], "HorizontalPodAutoscalerList"
        )
    except ApiException as e:
        raise api_error(e)


def get_hpa_data(namespace: str, name: str) -> Dict[str, Any]:
    try:
        return summarize_hpa(
            autoscaling_v2.read_namespaced_horizontal_pod_autoscaler(
                validated_name(name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "HorizontalPodAutoscaler not found")


def list_ingresses_data(namespace: str) -> Dict[str, Any]:
    try:
        ings = networking_v1.list_namespaced_ingress(validated_name(namespace))
        return list_response([summarize_ingress(i) for i in ings.items], "IngressList")
    except ApiException as e:
        raise api_error(e)


def get_ingress_data(namespace: str, name: str) -> Dict[str, Any]:
    try:
        return summarize_ingress(
            networking_v1.read_namespaced_ingress(
                validated_name(name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Ingress not found")


def list_network_policies_data(namespace: str) -> Dict[str, Any]:
    try:
        nps = networking_v1.list_namespaced_network_policy(validated_name(namespace))
        return list_response(
            [summarize_network_policy(n) for n in nps.items], "NetworkPolicyList"
        )
    except ApiException as e:
        raise api_error(e)


# ============================================================
# Data functions — Kubernetes batch / RBAC
# ============================================================
def list_jobs_data(namespace: str) -> Dict[str, Any]:
    try:
        jobs = batch_v1.list_namespaced_job(validated_name(namespace))
        return list_response([summarize_job(j) for j in jobs.items], "JobList")
    except ApiException as e:
        raise api_error(e)


def get_job_data(namespace: str, job_name: str) -> Dict[str, Any]:
    try:
        return summarize_job(
            batch_v1.read_namespaced_job(
                validated_name(job_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Job not found")


def list_cronjobs_data(namespace: str) -> Dict[str, Any]:
    try:
        cjs = batch_v1.list_namespaced_cron_job(validated_name(namespace))
        return list_response([summarize_cronjob(c) for c in cjs.items], "CronJobList")
    except ApiException as e:
        raise api_error(e)


def get_cronjob_data(namespace: str, cronjob_name: str) -> Dict[str, Any]:
    try:
        return summarize_cronjob(
            batch_v1.read_namespaced_cron_job(
                validated_name(cronjob_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "CronJob not found")


def list_roles_data(namespace: str) -> Dict[str, Any]:
    try:
        roles = rbac_v1.list_namespaced_role(validated_name(namespace))
        return list_response([summarize_role(r) for r in roles.items], "RoleList")
    except ApiException as e:
        raise api_error(e)


def get_role_data(namespace: str, role_name: str) -> Dict[str, Any]:
    try:
        return summarize_role(
            rbac_v1.read_namespaced_role(
                validated_name(role_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Role not found")


def list_role_bindings_data(namespace: str) -> Dict[str, Any]:
    try:
        bindings = rbac_v1.list_namespaced_role_binding(validated_name(namespace))
        return list_response(
            [summarize_binding(b) for b in bindings.items], "RoleBindingList"
        )
    except ApiException as e:
        raise api_error(e)


def get_role_binding_data(namespace: str, role_binding_name: str) -> Dict[str, Any]:
    try:
        return summarize_binding(
            rbac_v1.read_namespaced_role_binding(
                validated_name(role_binding_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "RoleBinding not found")


def list_cluster_roles_data() -> Dict[str, Any]:
    try:
        roles = rbac_v1.list_cluster_role()
        return list_response(
            [summarize_role(r) for r in roles.items], "ClusterRoleList"
        )
    except ApiException as e:
        raise api_error(e)


def get_cluster_role_data(cluster_role_name: str) -> Dict[str, Any]:
    try:
        return summarize_role(
            rbac_v1.read_cluster_role(validated_name(cluster_role_name))
        )
    except ApiException as e:
        raise api_error(e, "ClusterRole not found")


def list_cluster_role_bindings_data() -> Dict[str, Any]:
    try:
        bindings = rbac_v1.list_cluster_role_binding()
        return list_response(
            [summarize_binding(b) for b in bindings.items], "ClusterRoleBindingList"
        )
    except ApiException as e:
        raise api_error(e)


def get_cluster_role_binding_data(cluster_role_binding_name: str) -> Dict[str, Any]:
    try:
        return summarize_binding(
            rbac_v1.read_cluster_role_binding(validated_name(cluster_role_binding_name))
        )
    except ApiException as e:
        raise api_error(e, "ClusterRoleBinding not found")


# ============================================================
# Data functions — OpenShift custom resources
# ============================================================
def _list_namespaced(
    group: str, version: str, namespace: str, plural: str, summarizer, kind: str
) -> Dict[str, Any]:
    try:
        result = custom_objects.list_namespaced_custom_object(
            group, version, validated_name(namespace), plural
        )
        return list_response(
            [summarizer(item) for item in result.get("items", [])], kind
        )
    except ApiException as e:
        if e.status == 404:
            raise crd_not_available(kind)
        raise api_error(e)


def _get_namespaced(
    group: str,
    version: str,
    namespace: str,
    plural: str,
    name: str,
    summarizer,
    not_found_msg: str,
) -> Dict[str, Any]:
    try:
        obj = custom_objects.get_namespaced_custom_object(
            group, version, validated_name(namespace), plural, validated_name(name)
        )
        return summarizer(obj)
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=not_found_msg)
        raise api_error(e)


def _list_cluster(
    group: str, version: str, plural: str, summarizer, kind: str
) -> Dict[str, Any]:
    try:
        result = custom_objects.list_cluster_custom_object(group, version, plural)
        return list_response(
            [summarizer(item) for item in result.get("items", [])], kind
        )
    except ApiException as e:
        if e.status == 404:
            raise crd_not_available(kind)
        raise api_error(e)


def _get_cluster(
    group: str, version: str, plural: str, name: str, summarizer, not_found_msg: str
) -> Dict[str, Any]:
    try:
        obj = custom_objects.get_cluster_custom_object(
            group, version, plural, validated_name(name)
        )
        return summarizer(obj)
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=not_found_msg)
        raise api_error(e)


# OpenShift Routes
def list_routes_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_ROUTE_GROUP,
        OPENSHIFT_ROUTE_VERSION,
        namespace,
        OPENSHIFT_ROUTE_PLURAL,
        summarize_route,
        "RouteList",
    )


def get_route_data(namespace: str, route_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_ROUTE_GROUP,
        OPENSHIFT_ROUTE_VERSION,
        namespace,
        OPENSHIFT_ROUTE_PLURAL,
        route_name,
        summarize_route,
        "Route not found",
    )


# OpenShift Projects
def list_projects_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_PROJECT_GROUP,
        OPENSHIFT_PROJECT_VERSION,
        OPENSHIFT_PROJECT_PLURAL,
        summarize_project,
        "ProjectList",
    )


def get_project_data(project_name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_PROJECT_GROUP,
        OPENSHIFT_PROJECT_VERSION,
        OPENSHIFT_PROJECT_PLURAL,
        project_name,
        summarize_project,
        "Project not found",
    )


# OpenShift DeploymentConfigs
def list_deployment_configs_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_APPS_GROUP,
        OPENSHIFT_APPS_VERSION,
        namespace,
        "deploymentconfigs",
        summarize_deployment_config,
        "DeploymentConfigList",
    )


def get_deployment_config_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_APPS_GROUP,
        OPENSHIFT_APPS_VERSION,
        namespace,
        "deploymentconfigs",
        name,
        summarize_deployment_config,
        "DeploymentConfig not found",
    )


def rollout_restart_deployment_config_data(namespace: str, name: str) -> Dict[str, Any]:
    path = f"/apis/apps.openshift.io/v1/namespaces/{validated_name(namespace)}/deploymentconfigs/{validated_name(name)}/instantiate"
    body = {
        "kind": "DeploymentRequest",
        "apiVersion": "apps.openshift.io/v1",
        "name": name,
        "force": True,
        "latest": True,
    }
    try:
        custom_objects.api_client.call_api(
            path,
            "POST",
            header_params={"Content-Type": "application/json"},
            body=body,
            response_types_map={200: "object", 201: "object"},
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _preload_content=False,
        )
        return {"status": "rollout_requested", "name": name, "namespace": namespace}
    except ApiException as e:
        raise api_error(e, "DeploymentConfig not found")


# OpenShift BuildConfigs / Builds
def list_build_configs_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "buildconfigs",
        summarize_build_config,
        "BuildConfigList",
    )


def get_build_config_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "buildconfigs",
        name,
        summarize_build_config,
        "BuildConfig not found",
    )


def list_builds_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "builds",
        summarize_build,
        "BuildList",
    )


def get_build_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "builds",
        name,
        summarize_build,
        "Build not found",
    )


# OpenShift ImageStreams
def list_image_streams_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_IMAGE_GROUP,
        OPENSHIFT_IMAGE_VERSION,
        namespace,
        "imagestreams",
        summarize_image_stream,
        "ImageStreamList",
    )


def get_image_stream_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_IMAGE_GROUP,
        OPENSHIFT_IMAGE_VERSION,
        namespace,
        "imagestreams",
        name,
        summarize_image_stream,
        "ImageStream not found",
    )


# OpenShift Security Context Constraints
def list_sccs_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_SECURITY_GROUP,
        OPENSHIFT_SECURITY_VERSION,
        "securitycontextconstraints",
        summarize_scc,
        "SecurityContextConstraintList",
    )


def get_scc_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_SECURITY_GROUP,
        OPENSHIFT_SECURITY_VERSION,
        "securitycontextconstraints",
        name,
        summarize_scc,
        "SecurityContextConstraint not found",
    )


# OpenShift Users / Groups
def list_users_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "users",
        summarize_user,
        "UserList",
    )


def get_user_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "users",
        name,
        summarize_user,
        "User not found",
    )


def list_groups_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "groups",
        summarize_group,
        "GroupList",
    )


def get_group_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "groups",
        name,
        summarize_group,
        "Group not found",
    )


# OpenShift ClusterVersion / ClusterOperators
def get_cluster_version_data() -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_CONFIG_GROUP,
        OPENSHIFT_CONFIG_VERSION,
        "clusterversions",
        "version",
        summarize_cluster_version,
        "ClusterVersion not found",
    )


def list_cluster_operators_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_CONFIG_GROUP,
        OPENSHIFT_CONFIG_VERSION,
        "clusteroperators",
        summarize_cluster_operator,
        "ClusterOperatorList",
    )


def get_cluster_operator_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_CONFIG_GROUP,
        OPENSHIFT_CONFIG_VERSION,
        "clusteroperators",
        name,
        summarize_cluster_operator,
        "ClusterOperator not found",
    )


# Machine Config
def list_machine_config_pools_data() -> Dict[str, Any]:
    return _list_cluster(
        MACHINE_CONFIG_GROUP,
        MACHINE_CONFIG_VERSION,
        "machineconfigpools",
        summarize_machine_config_pool,
        "MachineConfigPoolList",
    )


def get_machine_config_pool_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        MACHINE_CONFIG_GROUP,
        MACHINE_CONFIG_VERSION,
        "machineconfigpools",
        name,
        summarize_machine_config_pool,
        "MachineConfigPool not found",
    )


# Machine API
def list_machines_data(namespace: str = "openshift-machine-api") -> Dict[str, Any]:
    return _list_namespaced(
        MACHINE_GROUP,
        MACHINE_VERSION,
        namespace,
        "machines",
        summarize_machine,
        "MachineList",
    )


def list_machine_sets_data(namespace: str = "openshift-machine-api") -> Dict[str, Any]:
    return _list_namespaced(
        MACHINE_GROUP,
        MACHINE_VERSION,
        namespace,
        "machinesets",
        summarize_machine_set,
        "MachineSetList",
    )


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


# KubeVirt VMs / VMIs
def list_virtualmachines_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VM_PLURAL,
        summarize_virtualmachine,
        "VirtualMachineList",
    )


def get_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VM_PLURAL,
        vm_name,
        summarize_virtualmachine,
        "VirtualMachine not found",
    )


def list_vmis_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VMI_PLURAL,
        summarize_vmi,
        "VirtualMachineInstanceList",
    )


def get_vmi_data(namespace: str, vmi_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VMI_PLURAL,
        vmi_name,
        summarize_vmi,
        "VirtualMachineInstance not found",
    )


def _vm_power_action(namespace: str, vm_name: str, action: str) -> Dict[str, Any]:
    path = f"/apis/subresources.kubevirt.io/v1/namespaces/{validated_name(namespace)}/virtualmachines/{validated_name(vm_name)}/{action}"
    try:
        custom_objects.api_client.call_api(
            path,
            "PUT",
            header_params={"Content-Type": "application/json"},
            body={},
            response_types_map={200: "object", 202: "object", 204: "object"},
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _preload_content=False,
        )
    except ApiException as e:
        raise api_error(e, "VirtualMachine not found")
    return {"status": f"vm_{action}_requested", "name": vm_name, "namespace": namespace}


def clone_virtualmachine_data(
    namespace: str, vm_name: str, new_vm_name: str
) -> Dict[str, Any]:
    try:
        vm = get_virtualmachine_data(namespace, vm_name)
        vm_obj = custom_objects.get_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            KUBEVIRT_VM_PLURAL,
            validated_name(vm_name),
        )
        spec = vm_obj.get("spec", {})
        new_spec = {"metadata": {"name": validated_name(new_vm_name)}, "spec": spec}
        result = custom_objects.create_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            KUBEVIRT_VM_PLURAL,
            new_spec,
        )
        return {
            "status": "clone_requested",
            "source_vm": vm_name,
            "cloned_vm": new_vm_name,
            "namespace": namespace,
        }
    except ApiException as e:
        raise api_error(e, "VirtualMachine not found or clone failed")


def pause_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    return _vm_power_action(namespace, vm_name, "pause")


def unpause_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    return _vm_power_action(namespace, vm_name, "unpause")


def force_reboot_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    path = f"/apis/subresources.kubevirt.io/v1/namespaces/{validated_name(namespace)}/virtualmachines/{validated_name(vm_name)}/reboot"
    body = {"force": True}
    try:
        custom_objects.api_client.call_api(
            path,
            "PUT",
            header_params={"Content-Type": "application/json"},
            body=body,
            response_types_map={200: "object", 202: "object", 204: "object"},
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _preload_content=False,
        )
    except ApiException as e:
        raise api_error(e, "VirtualMachine not found")
    return {"status": "force_reboot_requested", "name": vm_name, "namespace": namespace}


def list_vm_snapshots_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        "virtualmachinesnapshots",
        lambda s: s,
        "VirtualMachineSnapshotList",
    )


def create_vm_snapshot_data(
    namespace: str, vm_name: str, snapshot_name: str
) -> Dict[str, Any]:
    try:
        snapshot_obj = {
            "apiVersion": f"{KUBEVIRT_GROUP}/{KUBEVIRT_VERSION}",
            "kind": "VirtualMachineSnapshot",
            "metadata": {"name": validated_name(snapshot_name)},
            "spec": {
                "source": {"name": validated_name(vm_name), "kind": "VirtualMachine"}
            },
        }
        result = custom_objects.create_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            "virtualmachinesnapshots",
            snapshot_obj,
        )
        return {
            "status": "snapshot_requested",
            "snapshot_name": snapshot_name,
            "vm_name": vm_name,
            "namespace": namespace,
        }
    except ApiException as e:
        raise api_error(e, "Could not create snapshot")


def delete_vm_snapshot_data(namespace: str, snapshot_name: str) -> Dict[str, Any]:
    try:
        custom_objects.delete_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            "virtualmachinesnapshots",
            validated_name(snapshot_name),
        )
        return {
            "status": "snapshot_deleted",
            "snapshot_name": snapshot_name,
            "namespace": namespace,
        }
    except ApiException as e:
        raise api_error(e, "Snapshot not found")


def list_data_volumes_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        "cdi.kubevirt.io",
        "v1beta1",
        namespace,
        "datavolumes",
        lambda d: d,
        "DataVolumeList",
    )


def get_data_volume_data(namespace: str, dv_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        "cdi.kubevirt.io",
        "v1beta1",
        namespace,
        "datavolumes",
        dv_name,
        lambda d: d,
        "DataVolume not found",
    )


def get_vm_console_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    try:
        vmi = custom_objects.get_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            KUBEVIRT_VMI_PLURAL,
            validated_name(vm_name),
        )
        status = vmi.get("status", {})
        graphics = status.get("graphics", [])
        return {
            "vm_name": vm_name,
            "namespace": namespace,
            "console_available": len(graphics) > 0,
            "graphics": graphics,
            "access_credentials": status.get("accessCredentials"),
        }
    except ApiException as e:
        raise api_error(e, "VirtualMachineInstance not found or no console available")


def list_vm_restores_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        "virtualmachinerestores",
        lambda r: r,
        "VirtualMachineRestoreList",
    )


# ============================================================
# MCP server
# ============================================================
MCP_STATELESS_HTTP = True
MCP_JSON_RESPONSE = True
MCP_STREAMABLE_HTTP_PATH = "/"
MCP_TRANSPORT_SECURITY = TransportSecuritySettings(
    allowed_hosts=csv_env(
        "MCP_ALLOWED_HOSTS",
        ["127.0.0.1:*", "localhost:*", "[::1]:*"],
    ),
    allowed_origins=csv_env(
        "MCP_ALLOWED_ORIGINS",
        ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    ),
)


def accepted_kwargs(callable_obj: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    signature = inspect.signature(callable_obj)
    parameters = signature.parameters.values()
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in signature.parameters}


MCP_TRANSPORT_KWARGS = {
    "stateless_http": MCP_STATELESS_HTTP,
    "json_response": MCP_JSON_RESPONSE,
    "streamable_http_path": MCP_STREAMABLE_HTTP_PATH,
    "transport_security": MCP_TRANSPORT_SECURITY,
}

mcp = FastMCP(
    "OpenShift Admin Operations",
    instructions=(
        "Full administrative access to Kubernetes/OpenShift clusters. "
        "Read: namespaces, projects, nodes, pods, logs, events, containers, services, "
        "deployments, statefulsets, daemonsets, replicasets, HPAs, ingresses, network policies, "
        "jobs, cronjobs, PVs, PVCs, storage classes, config maps, service accounts, "
        "resource quotas, limit ranges, RBAC, routes, build configs, builds, image streams, "
        "SCCs, users, groups, cluster version, cluster operators, machine config pools, "
        "machines, machine sets, OLM subscriptions, installed operators, catalog sources, "
        "KubeVirt VMs and VMIs. "
        "Mutate: restart/scale deployments and statefulsets, delete pods, update resources, "
        "trigger DC rollouts, start/stop/restart VMs."
    ),
    **accepted_kwargs(FastMCP, MCP_TRANSPORT_KWARGS),
)


# --- MCP tools: namespaces ---
@mcp.tool()
def list_namespaces() -> Dict[str, Any]:
    """List all Kubernetes namespaces with status, labels and annotations."""
    return list_namespaces_data()


@mcp.tool()
def get_namespace(namespace: str) -> Dict[str, Any]:
    """Get details for one Kubernetes namespace."""
    return get_namespace_data(namespace)


# --- MCP tools: nodes ---
@mcp.tool()
def list_nodes(label_selector: Optional[str] = None) -> Dict[str, Any]:
    """List cluster nodes with roles, capacity, allocatable resources and conditions."""
    return list_nodes_data(label_selector)


@mcp.tool()
def get_node(node_name: str) -> Dict[str, Any]:
    """Get detailed info for one cluster node including taints and hardware info."""
    return get_node_data(node_name)


# --- MCP tools: pods ---
@mcp.tool()
def list_pods(namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
    """List pods in a namespace, optionally filtered by label selector."""
    return list_pods_data(namespace, label_selector)


@mcp.tool()
def get_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get one pod with container statuses, restart counts, resources and conditions."""
    return get_pod_data(namespace, pod_name)


@mcp.tool()
def get_pod_logs(
    namespace: str,
    pod_name: str,
    container: Optional[str] = None,
    tail_lines: int = 200,
    since_seconds: Optional[int] = None,
    previous: bool = False,
) -> Dict[str, Any]:
    """Read logs from a pod container."""
    return get_pod_logs_data(
        namespace,
        pod_name,
        LogQuery(
            container=container,
            tail_lines=tail_lines,
            since_seconds=since_seconds,
            previous=previous,
        ),
    )


@mcp.tool()
def delete_pod(
    namespace: str,
    pod_name: str,
    grace_period_seconds: Optional[int] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Delete a pod. Use force=True to set grace period to 0."""
    return delete_pod_data(
        namespace,
        pod_name,
        DeleteOptions(grace_period_seconds=grace_period_seconds, force=force),
    )


@mcp.tool()
def list_containers(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    """List containers across pods in a namespace with image, readiness, restarts and resources."""
    return list_containers_data(namespace, label_selector)


# --- MCP tools: events ---
@mcp.tool()
def list_events(
    namespace: str,
    involved_object_name: Optional[str] = None,
    involved_object_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """List namespace events, optionally filtered by involved object name and kind."""
    return list_events_data(namespace, involved_object_name, involved_object_kind)


# --- MCP tools: services ---
@mcp.tool()
def list_services(namespace: str) -> Dict[str, Any]:
    """List services in a namespace."""
    return list_services_data(namespace)


@mcp.tool()
def get_service(namespace: str, service_name: str) -> Dict[str, Any]:
    """Get one service in a namespace."""
    return get_service_data(namespace, service_name)


# --- MCP tools: deployments ---
@mcp.tool()
def list_deployments(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    """List deployments in a namespace with rollout and container resource summaries."""
    return list_deployments_data(namespace, label_selector)


@mcp.tool()
def get_deployment(namespace: str, deployment_name: str) -> Dict[str, Any]:
    """Get one deployment with rollout status and container resources."""
    return get_deployment_data(namespace, deployment_name)


@mcp.tool()
def rollout_restart_deployment(namespace: str, deployment_name: str) -> Dict[str, Any]:
    """Request a rollout restart for one deployment."""
    return rollout_restart_deployment_data(namespace, deployment_name)


@mcp.tool()
def scale_deployment(
    namespace: str, deployment_name: str, replicas: int
) -> Dict[str, Any]:
    """Scale a deployment to the given number of replicas (0–500)."""
    if replicas < 0 or replicas > 500:
        raise HTTPException(
            status_code=400, detail="replicas must be between 0 and 500"
        )
    return scale_deployment_data(namespace, deployment_name, replicas)


@mcp.tool()
def update_deployment_container_resources(
    namespace: str,
    deployment_name: str,
    container_name: str,
    limits: Optional[Dict[str, str]] = None,
    requests: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Update CPU/memory limits and requests for one deployment container."""
    return update_deployment_container_resources_data(
        namespace,
        deployment_name,
        container_name,
        ResourceRequirementsPatch(limits=limits, requests=requests),
    )


# --- MCP tools: statefulsets ---
@mcp.tool()
def list_statefulsets(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    """List StatefulSets in a namespace."""
    return list_statefulsets_data(namespace, label_selector)


@mcp.tool()
def get_statefulset(namespace: str, statefulset_name: str) -> Dict[str, Any]:
    """Get one StatefulSet with replica counts and container info."""
    return get_statefulset_data(namespace, statefulset_name)


@mcp.tool()
def rollout_restart_statefulset(
    namespace: str, statefulset_name: str
) -> Dict[str, Any]:
    """Request a rollout restart for one StatefulSet."""
    return rollout_restart_statefulset_data(namespace, statefulset_name)


@mcp.tool()
def scale_statefulset(
    namespace: str, statefulset_name: str, replicas: int
) -> Dict[str, Any]:
    """Scale a StatefulSet to the given number of replicas (0–500)."""
    if replicas < 0 or replicas > 500:
        raise HTTPException(
            status_code=400, detail="replicas must be between 0 and 500"
        )
    return scale_statefulset_data(namespace, statefulset_name, replicas)


# --- MCP tools: daemonsets / replicasets ---
@mcp.tool()
def list_daemonsets(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    """List DaemonSets in a namespace with scheduling and readiness counts."""
    return list_daemonsets_data(namespace, label_selector)


@mcp.tool()
def get_daemonset(namespace: str, daemonset_name: str) -> Dict[str, Any]:
    """Get one DaemonSet with scheduling and readiness details."""
    return get_daemonset_data(namespace, daemonset_name)


@mcp.tool()
def list_replicasets(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    """List ReplicaSets in a namespace."""
    return list_replicasets_data(namespace, label_selector)


# --- MCP tools: HPAs ---
@mcp.tool()
def list_hpas(namespace: str) -> Dict[str, Any]:
    """List HorizontalPodAutoscalers in a namespace."""
    return list_hpas_data(namespace)


@mcp.tool()
def get_hpa(namespace: str, hpa_name: str) -> Dict[str, Any]:
    """Get one HorizontalPodAutoscaler with current/desired replicas and metrics."""
    return get_hpa_data(namespace, hpa_name)


# --- MCP tools: ingresses / network policies ---
@mcp.tool()
def list_ingresses(namespace: str) -> Dict[str, Any]:
    """List Ingresses in a namespace."""
    return list_ingresses_data(namespace)


@mcp.tool()
def get_ingress(namespace: str, ingress_name: str) -> Dict[str, Any]:
    """Get one Ingress with rules, TLS and load balancer info."""
    return get_ingress_data(namespace, ingress_name)


@mcp.tool()
def list_network_policies(namespace: str) -> Dict[str, Any]:
    """List NetworkPolicies in a namespace with ingress/egress rules."""
    return list_network_policies_data(namespace)


# --- MCP tools: storage ---
@mcp.tool()
def list_persistent_volumes() -> Dict[str, Any]:
    """List cluster-wide PersistentVolumes with capacity and claim info."""
    return list_persistent_volumes_data()


@mcp.tool()
def get_persistent_volume(pv_name: str) -> Dict[str, Any]:
    """Get one PersistentVolume."""
    return get_persistent_volume_data(pv_name)


@mcp.tool()
def list_storage_classes() -> Dict[str, Any]:
    """List cluster StorageClasses with provisioner and reclaim policy."""
    return list_storage_classes_data()


@mcp.tool()
def list_persistent_volume_claims(namespace: str) -> Dict[str, Any]:
    """List PersistentVolumeClaims in a namespace."""
    return list_pvcs_data(namespace)


@mcp.tool()
def get_persistent_volume_claim(namespace: str, pvc_name: str) -> Dict[str, Any]:
    """Get one PersistentVolumeClaim."""
    return get_pvc_data(namespace, pvc_name)


# --- MCP tools: config maps / service accounts ---
@mcp.tool()
def list_config_maps(namespace: str) -> Dict[str, Any]:
    """List ConfigMaps in a namespace with their data. May contain sensitive values."""
    return list_config_maps_data(namespace)


@mcp.tool()
def get_config_map(namespace: str, config_map_name: str) -> Dict[str, Any]:
    """Get one ConfigMap including its data keys and values."""
    return get_config_map_data(namespace, config_map_name)


@mcp.tool()
def list_service_accounts(namespace: str) -> Dict[str, Any]:
    """List ServiceAccounts in a namespace."""
    return list_service_accounts_data(namespace)


@mcp.tool()
def get_service_account(namespace: str, service_account_name: str) -> Dict[str, Any]:
    """Get one ServiceAccount with secret refs."""
    return get_service_account_data(namespace, service_account_name)


# --- MCP tools: quotas / limits ---
@mcp.tool()
def list_resource_quotas(namespace: str) -> Dict[str, Any]:
    """List ResourceQuotas in a namespace showing hard limits and current usage."""
    return list_resource_quotas_data(namespace)


@mcp.tool()
def get_resource_quota(namespace: str, resource_quota_name: str) -> Dict[str, Any]:
    """Get one ResourceQuota with hard limits and usage."""
    return get_resource_quota_data(namespace, resource_quota_name)


@mcp.tool()
def list_limit_ranges(namespace: str) -> Dict[str, Any]:
    """List LimitRanges in a namespace."""
    return list_limit_ranges_data(namespace)


# --- MCP tools: jobs / cronjobs ---
@mcp.tool()
def list_jobs(namespace: str) -> Dict[str, Any]:
    """List Kubernetes Jobs in a namespace."""
    return list_jobs_data(namespace)


@mcp.tool()
def get_job(namespace: str, job_name: str) -> Dict[str, Any]:
    """Get one Kubernetes Job."""
    return get_job_data(namespace, job_name)


@mcp.tool()
def list_cronjobs(namespace: str) -> Dict[str, Any]:
    """List Kubernetes CronJobs in a namespace."""
    return list_cronjobs_data(namespace)


@mcp.tool()
def get_cronjob(namespace: str, cronjob_name: str) -> Dict[str, Any]:
    """Get one Kubernetes CronJob."""
    return get_cronjob_data(namespace, cronjob_name)


# --- MCP tools: RBAC ---
@mcp.tool()
def list_rbac(namespace: str) -> Dict[str, Any]:
    """List Roles and RoleBindings in a namespace."""
    return {
        "roles": list_roles_data(namespace),
        "role_bindings": list_role_bindings_data(namespace),
    }


@mcp.tool()
def list_cluster_rbac() -> Dict[str, Any]:
    """List ClusterRoles and ClusterRoleBindings."""
    return {
        "cluster_roles": list_cluster_roles_data(),
        "cluster_role_bindings": list_cluster_role_bindings_data(),
    }


# --- MCP tools: OpenShift routes ---
@mcp.tool()
def list_routes(namespace: str) -> Dict[str, Any]:
    """List OpenShift Routes in a namespace."""
    return list_routes_data(namespace)


@mcp.tool()
def get_route(namespace: str, route_name: str) -> Dict[str, Any]:
    """Get one OpenShift Route."""
    return get_route_data(namespace, route_name)


# --- MCP tools: OpenShift projects ---
@mcp.tool()
def list_projects() -> Dict[str, Any]:
    """List OpenShift Projects (cluster-wide) with display name and status."""
    return list_projects_data()


@mcp.tool()
def get_project(project_name: str) -> Dict[str, Any]:
    """Get one OpenShift Project."""
    return get_project_data(project_name)


# --- MCP tools: OpenShift DeploymentConfigs ---
@mcp.tool()
def list_deployment_configs(namespace: str) -> Dict[str, Any]:
    """List OpenShift DeploymentConfigs in a namespace."""
    return list_deployment_configs_data(namespace)


@mcp.tool()
def get_deployment_config(namespace: str, dc_name: str) -> Dict[str, Any]:
    """Get one OpenShift DeploymentConfig with replica and trigger info."""
    return get_deployment_config_data(namespace, dc_name)


@mcp.tool()
def rollout_restart_deployment_config(namespace: str, dc_name: str) -> Dict[str, Any]:
    """Trigger a new rollout for an OpenShift DeploymentConfig."""
    return rollout_restart_deployment_config_data(namespace, dc_name)


# --- MCP tools: OpenShift builds ---
@mcp.tool()
def list_build_configs(namespace: str) -> Dict[str, Any]:
    """List OpenShift BuildConfigs in a namespace."""
    return list_build_configs_data(namespace)


@mcp.tool()
def get_build_config(namespace: str, build_config_name: str) -> Dict[str, Any]:
    """Get one OpenShift BuildConfig with source and strategy info."""
    return get_build_config_data(namespace, build_config_name)


@mcp.tool()
def list_builds(namespace: str) -> Dict[str, Any]:
    """List OpenShift Builds in a namespace with phase and timing."""
    return list_builds_data(namespace)


@mcp.tool()
def get_build(namespace: str, build_name: str) -> Dict[str, Any]:
    """Get one OpenShift Build with phase, output image and duration."""
    return get_build_data(namespace, build_name)


# --- MCP tools: OpenShift image streams ---
@mcp.tool()
def list_image_streams(namespace: str) -> Dict[str, Any]:
    """List OpenShift ImageStreams in a namespace."""
    return list_image_streams_data(namespace)


@mcp.tool()
def get_image_stream(namespace: str, image_stream_name: str) -> Dict[str, Any]:
    """Get one OpenShift ImageStream with tags and repository info."""
    return get_image_stream_data(namespace, image_stream_name)


# --- MCP tools: OpenShift security ---
@mcp.tool()
def list_security_context_constraints() -> Dict[str, Any]:
    """List OpenShift SecurityContextConstraints (cluster-wide)."""
    return list_sccs_data()


@mcp.tool()
def get_security_context_constraint(scc_name: str) -> Dict[str, Any]:
    """Get one OpenShift SecurityContextConstraint with privilege and volume settings."""
    return get_scc_data(scc_name)


# --- MCP tools: OpenShift users / groups ---
@mcp.tool()
def list_users() -> Dict[str, Any]:
    """List OpenShift Users with identities and group memberships."""
    return list_users_data()


@mcp.tool()
def get_user(user_name: str) -> Dict[str, Any]:
    """Get one OpenShift User."""
    return get_user_data(user_name)


@mcp.tool()
def list_groups() -> Dict[str, Any]:
    """List OpenShift Groups with their members."""
    return list_groups_data()


@mcp.tool()
def get_group(group_name: str) -> Dict[str, Any]:
    """Get one OpenShift Group with its user list."""
    return get_group_data(group_name)


# --- MCP tools: OpenShift cluster version / operators ---
@mcp.tool()
def get_cluster_version() -> Dict[str, Any]:
    """Get OpenShift cluster version, channel, available updates and conditions."""
    return get_cluster_version_data()


@mcp.tool()
def list_cluster_operators() -> Dict[str, Any]:
    """List all OpenShift ClusterOperators with available/progressing/degraded status."""
    return list_cluster_operators_data()


@mcp.tool()
def get_cluster_operator(operator_name: str) -> Dict[str, Any]:
    """Get one OpenShift ClusterOperator with conditions and version."""
    return get_cluster_operator_data(operator_name)


# --- MCP tools: Machine Config ---
@mcp.tool()
def list_machine_config_pools() -> Dict[str, Any]:
    """List MachineConfigPools showing node counts and update/degraded status."""
    return list_machine_config_pools_data()


@mcp.tool()
def get_machine_config_pool(pool_name: str) -> Dict[str, Any]:
    """Get one MachineConfigPool with counts and update conditions."""
    return get_machine_config_pool_data(pool_name)


# --- MCP tools: Machine API ---
@mcp.tool()
def list_machines(namespace: str = "openshift-machine-api") -> Dict[str, Any]:
    """List Machines in the Machine API namespace (default: openshift-machine-api)."""
    return list_machines_data(namespace)


@mcp.tool()
def list_machine_sets(namespace: str = "openshift-machine-api") -> Dict[str, Any]:
    """List MachineSets in the Machine API namespace."""
    return list_machine_sets_data(namespace)


# --- MCP tools: OLM ---
@mcp.tool()
def list_olm_subscriptions(namespace: str) -> Dict[str, Any]:
    """List OLM Subscriptions in a namespace showing channel and install state."""
    return list_subscriptions_data(namespace)


@mcp.tool()
def list_installed_operators(namespace: str) -> Dict[str, Any]:
    """List installed operators (ClusterServiceVersions) in a namespace with phase."""
    return list_installed_operators_data(namespace)


@mcp.tool()
def list_catalog_sources(namespace: str = "openshift-marketplace") -> Dict[str, Any]:
    """List OLM CatalogSources (default namespace: openshift-marketplace)."""
    return list_catalog_sources_data(namespace)


# --- MCP tools: KubeVirt ---
@mcp.tool()
def list_virtualmachines(namespace: str) -> Dict[str, Any]:
    """List KubeVirt VirtualMachines in a namespace."""
    return list_virtualmachines_data(namespace)


@mcp.tool()
def get_virtualmachine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Get one KubeVirt VirtualMachine with running state and status."""
    return get_virtualmachine_data(namespace, vm_name)


@mcp.tool()
def list_virtual_machine_instances(namespace: str) -> Dict[str, Any]:
    """List running KubeVirt VirtualMachineInstances in a namespace."""
    return list_vmis_data(namespace)


@mcp.tool()
def get_virtual_machine_instance(namespace: str, vmi_name: str) -> Dict[str, Any]:
    """Get one KubeVirt VirtualMachineInstance with phase, node and IP info."""
    return get_vmi_data(namespace, vmi_name)


@mcp.tool()
def start_virtual_machine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Start a stopped KubeVirt VirtualMachine."""
    return _vm_power_action(namespace, vm_name, "start")


@mcp.tool()
def stop_virtual_machine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Stop a running KubeVirt VirtualMachine."""
    return _vm_power_action(namespace, vm_name, "stop")


@mcp.tool()
def restart_virtual_machine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Restart a KubeVirt VirtualMachine."""
    return _vm_power_action(namespace, vm_name, "restart")


@mcp.tool()
def pause_virtual_machine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Pause a running KubeVirt VirtualMachine (different from stop — memory stays in VM)."""
    return pause_virtualmachine_data(namespace, vm_name)


@mcp.tool()
def unpause_virtual_machine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Resume a paused KubeVirt VirtualMachine."""
    return unpause_virtualmachine_data(namespace, vm_name)


@mcp.tool()
def force_reboot_virtual_machine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Force an immediate reboot of a KubeVirt VirtualMachine without graceful shutdown."""
    return force_reboot_virtualmachine_data(namespace, vm_name)


@mcp.tool()
def clone_virtual_machine(
    namespace: str, vm_name: str, new_vm_name: str
) -> Dict[str, Any]:
    """Clone a KubeVirt VirtualMachine to a new VM with the same spec."""
    return clone_virtualmachine_data(namespace, vm_name, new_vm_name)


@mcp.tool()
def list_vm_snapshots(namespace: str) -> Dict[str, Any]:
    """List VirtualMachineSnapshots in a namespace."""
    return list_vm_snapshots_data(namespace)


@mcp.tool()
def create_vm_snapshot(
    namespace: str, vm_name: str, snapshot_name: str
) -> Dict[str, Any]:
    """Create a snapshot of a KubeVirt VirtualMachine."""
    return create_vm_snapshot_data(namespace, vm_name, snapshot_name)


@mcp.tool()
def delete_vm_snapshot(namespace: str, snapshot_name: str) -> Dict[str, Any]:
    """Delete a VirtualMachineSnapshot."""
    return delete_vm_snapshot_data(namespace, snapshot_name)


@mcp.tool()
def list_data_volumes(namespace: str) -> Dict[str, Any]:
    """List DataVolumes (CDI) in a namespace — storage for VMs."""
    return list_data_volumes_data(namespace)


@mcp.tool()
def get_data_volume(namespace: str, data_volume_name: str) -> Dict[str, Any]:
    """Get one DataVolume with import/upload progress and phase."""
    return get_data_volume_data(namespace, data_volume_name)


@mcp.tool()
def get_vm_console(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Get VirtualMachineInstance console access info (VNC/SPICE endpoints and credentials)."""
    return get_vm_console_data(namespace, vm_name)


@mcp.tool()
def list_vm_restores(namespace: str) -> Dict[str, Any]:
    """List VirtualMachineRestores in a namespace (restore from snapshots)."""
    return list_vm_restores_data(namespace)


# ============================================================
# FastAPI app
# ============================================================
@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


def create_mcp_streamable_http_app():
    return mcp.streamable_http_app(
        **accepted_kwargs(mcp.streamable_http_app, MCP_TRANSPORT_KWARGS)
    )


app = FastAPI(
    title="OpenShift Admin MCP Server",
    version=APP_VERSION,
    description=(
        "Production REST and MCP server for full OpenShift/Kubernetes administration. "
        "Use /api/v1 for REST and /mcp for MCP Streamable HTTP."
    ),
    lifespan=lifespan,
)
app.mount("/mcp", create_mcp_streamable_http_app())


@app.exception_handler(MaxRetryError)
async def max_retry_error_handler(request: Request, exc: MaxRetryError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Kubernetes cluster is not available"},
    )


@app.exception_handler(NewConnectionError)
async def new_connection_error_handler(request: Request, exc: NewConnectionError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Kubernetes cluster is not available"},
    )


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    if any(
        request.url.path.startswith(p) for p in AUTH_PROTECTED_PREFIXES
    ) and not is_authorized_request(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid authentication token"},
            headers={"WWW-Authenticate": 'Bearer realm="mcp-openshift"'},
        )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


@app.get("/")
def root():
    return {
        "name": "OpenShift Admin MCP Server",
        "version": APP_VERSION,
        "rest": "/api/v1",
        "mcp": "/mcp",
        "docs": "/docs",
        "health": "/healthz",
        "ready": "/readyz",
    }


@app.get("/healthz")
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/readyz")
def ready():
    if not K8S_AVAILABLE:
        raise HTTPException(status_code=503, detail="Kubernetes client not configured")
    try:
        core_v1.get_api_resources()
        return {"status": "ready"}
    except ApiException as e:
        raise api_error(e)


# ============================================================
# REST endpoints
# ============================================================


# Namespaces
@app.get("/api/v1/namespaces")
def rest_list_namespaces():
    return list_namespaces_data()


@app.get("/api/v1/namespaces/{namespace}")
def rest_get_namespace(namespace: str):
    return get_namespace_data(namespace)


# Nodes
@app.get("/api/v1/nodes")
def rest_list_nodes(label_selector: Optional[str] = None):
    return list_nodes_data(label_selector)


@app.get("/api/v1/nodes/{node_name}")
def rest_get_node(node_name: str):
    return get_node_data(node_name)


# Pods
@app.get("/api/v1/namespaces/{namespace}/pods")
def rest_list_pods(namespace: str, label_selector: Optional[str] = None):
    return list_pods_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/pods/{pod_name}")
def rest_get_pod(namespace: str, pod_name: str):
    return get_pod_data(namespace, pod_name)


@app.delete("/api/v1/namespaces/{namespace}/pods/{pod_name}")
def rest_delete_pod(
    namespace: str, pod_name: str, options: Optional[DeleteOptions] = Body(default=None)
):
    return delete_pod_data(namespace, pod_name, options)


@app.get("/api/v1/namespaces/{namespace}/pods/{pod_name}/logs")
def rest_get_pod_logs(
    namespace: str,
    pod_name: str,
    container: Optional[str] = None,
    tail_lines: int = Query(default=200, ge=1, le=10000),
    since_seconds: Optional[int] = Query(default=None, ge=1),
    previous: bool = False,
):
    return get_pod_logs_data(
        namespace,
        pod_name,
        LogQuery(
            container=container,
            tail_lines=tail_lines,
            since_seconds=since_seconds,
            previous=previous,
        ),
    )


@app.get("/api/v1/namespaces/{namespace}/pods/{pod_name}/events")
def rest_list_pod_events(namespace: str, pod_name: str):
    return list_events_data(namespace, pod_name, "Pod")


@app.get("/api/v1/namespaces/{namespace}/containers")
def rest_list_containers(namespace: str, label_selector: Optional[str] = None):
    return list_containers_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/events")
def rest_list_events(
    namespace: str,
    involved_object_name: Optional[str] = None,
    involved_object_kind: Optional[str] = None,
):
    return list_events_data(namespace, involved_object_name, involved_object_kind)


# Services
@app.get("/api/v1/namespaces/{namespace}/services")
def rest_list_services(namespace: str):
    return list_services_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/services/{service_name}")
def rest_get_service(namespace: str, service_name: str):
    return get_service_data(namespace, service_name)


# Storage
@app.get("/api/v1/persistentvolumes")
def rest_list_pvs():
    return list_persistent_volumes_data()


@app.get("/api/v1/persistentvolumes/{pv_name}")
def rest_get_pv(pv_name: str):
    return get_persistent_volume_data(pv_name)


@app.get("/api/v1/storageclasses")
def rest_list_storage_classes():
    return list_storage_classes_data()


@app.get("/api/v1/namespaces/{namespace}/persistentvolumeclaims")
def rest_list_pvcs(namespace: str):
    return list_pvcs_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/persistentvolumeclaims/{pvc_name}")
def rest_get_pvc(namespace: str, pvc_name: str):
    return get_pvc_data(namespace, pvc_name)


# ConfigMaps
@app.get("/api/v1/namespaces/{namespace}/configmaps")
def rest_list_config_maps(namespace: str):
    return list_config_maps_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/configmaps/{cm_name}")
def rest_get_config_map(namespace: str, cm_name: str):
    return get_config_map_data(namespace, cm_name)


# ServiceAccounts
@app.get("/api/v1/namespaces/{namespace}/serviceaccounts")
def rest_list_service_accounts(namespace: str):
    return list_service_accounts_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/serviceaccounts/{sa_name}")
def rest_get_service_account(namespace: str, sa_name: str):
    return get_service_account_data(namespace, sa_name)


# ResourceQuotas / LimitRanges
@app.get("/api/v1/namespaces/{namespace}/resourcequotas")
def rest_list_resource_quotas(namespace: str):
    return list_resource_quotas_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/resourcequotas/{rq_name}")
def rest_get_resource_quota(namespace: str, rq_name: str):
    return get_resource_quota_data(namespace, rq_name)


@app.get("/api/v1/namespaces/{namespace}/limitranges")
def rest_list_limit_ranges(namespace: str):
    return list_limit_ranges_data(namespace)


# Deployments
@app.get("/api/v1/namespaces/{namespace}/deployments")
def rest_list_deployments(namespace: str, label_selector: Optional[str] = None):
    return list_deployments_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/deployments/{deployment_name}")
def rest_get_deployment(namespace: str, deployment_name: str):
    return get_deployment_data(namespace, deployment_name)


@app.post(
    "/api/v1/namespaces/{namespace}/deployments/{deployment_name}/rollout/restart"
)
def rest_rollout_restart_deployment(namespace: str, deployment_name: str):
    return rollout_restart_deployment_data(namespace, deployment_name)


@app.get("/api/v1/namespaces/{namespace}/deployments/{deployment_name}/rollout/status")
def rest_get_deployment_rollout_status(namespace: str, deployment_name: str):
    return get_deployment_data(namespace, deployment_name)


@app.post("/api/v1/namespaces/{namespace}/deployments/{deployment_name}/scale")
def rest_scale_deployment(namespace: str, deployment_name: str, body: ScaleRequest):
    return scale_deployment_data(namespace, deployment_name, body.replicas)


@app.patch(
    "/api/v1/namespaces/{namespace}/deployments/{deployment_name}/containers/{container_name}/resources"
)
def rest_update_deployment_container_resources(
    namespace: str,
    deployment_name: str,
    container_name: str,
    resources: ResourceRequirementsPatch,
):
    return update_deployment_container_resources_data(
        namespace, deployment_name, container_name, resources
    )


# StatefulSets
@app.get("/api/v1/namespaces/{namespace}/statefulsets")
def rest_list_statefulsets(namespace: str, label_selector: Optional[str] = None):
    return list_statefulsets_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/statefulsets/{name}")
def rest_get_statefulset(namespace: str, name: str):
    return get_statefulset_data(namespace, name)


@app.post("/api/v1/namespaces/{namespace}/statefulsets/{name}/rollout/restart")
def rest_rollout_restart_statefulset(namespace: str, name: str):
    return rollout_restart_statefulset_data(namespace, name)


@app.post("/api/v1/namespaces/{namespace}/statefulsets/{name}/scale")
def rest_scale_statefulset(namespace: str, name: str, body: ScaleRequest):
    return scale_statefulset_data(namespace, name, body.replicas)


# DaemonSets / ReplicaSets
@app.get("/api/v1/namespaces/{namespace}/daemonsets")
def rest_list_daemonsets(namespace: str, label_selector: Optional[str] = None):
    return list_daemonsets_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/daemonsets/{name}")
def rest_get_daemonset(namespace: str, name: str):
    return get_daemonset_data(namespace, name)


@app.get("/api/v1/namespaces/{namespace}/replicasets")
def rest_list_replicasets(namespace: str, label_selector: Optional[str] = None):
    return list_replicasets_data(namespace, label_selector)


# HPAs
@app.get("/api/v1/namespaces/{namespace}/hpas")
def rest_list_hpas(namespace: str):
    return list_hpas_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/hpas/{name}")
def rest_get_hpa(namespace: str, name: str):
    return get_hpa_data(namespace, name)


# Ingresses / NetworkPolicies
@app.get("/api/v1/namespaces/{namespace}/ingresses")
def rest_list_ingresses(namespace: str):
    return list_ingresses_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/ingresses/{name}")
def rest_get_ingress(namespace: str, name: str):
    return get_ingress_data(namespace, name)


@app.get("/api/v1/namespaces/{namespace}/networkpolicies")
def rest_list_network_policies(namespace: str):
    return list_network_policies_data(namespace)


# Jobs / CronJobs
@app.get("/api/v1/namespaces/{namespace}/jobs")
def rest_list_jobs(namespace: str):
    return list_jobs_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/jobs/{job_name}")
def rest_get_job(namespace: str, job_name: str):
    return get_job_data(namespace, job_name)


@app.get("/api/v1/namespaces/{namespace}/cronjobs")
def rest_list_cronjobs(namespace: str):
    return list_cronjobs_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/cronjobs/{cronjob_name}")
def rest_get_cronjob(namespace: str, cronjob_name: str):
    return get_cronjob_data(namespace, cronjob_name)


# RBAC
@app.get("/api/v1/namespaces/{namespace}/rbac/roles")
def rest_list_roles(namespace: str):
    return list_roles_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/rbac/roles/{role_name}")
def rest_get_role(namespace: str, role_name: str):
    return get_role_data(namespace, role_name)


@app.get("/api/v1/namespaces/{namespace}/rbac/rolebindings")
def rest_list_role_bindings(namespace: str):
    return list_role_bindings_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/rbac/rolebindings/{role_binding_name}")
def rest_get_role_binding(namespace: str, role_binding_name: str):
    return get_role_binding_data(namespace, role_binding_name)


@app.get("/api/v1/rbac/clusterroles")
def rest_list_cluster_roles():
    return list_cluster_roles_data()


@app.get("/api/v1/rbac/clusterroles/{cluster_role_name}")
def rest_get_cluster_role(cluster_role_name: str):
    return get_cluster_role_data(cluster_role_name)


@app.get("/api/v1/rbac/clusterrolebindings")
def rest_list_cluster_role_bindings():
    return list_cluster_role_bindings_data()


@app.get("/api/v1/rbac/clusterrolebindings/{cluster_role_binding_name}")
def rest_get_cluster_role_binding(cluster_role_binding_name: str):
    return get_cluster_role_binding_data(cluster_role_binding_name)


# OpenShift routes
@app.get("/api/v1/namespaces/{namespace}/routes")
def rest_list_routes(namespace: str):
    return list_routes_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/routes/{route_name}")
def rest_get_route(namespace: str, route_name: str):
    return get_route_data(namespace, route_name)


# OpenShift projects
@app.get("/api/v1/projects")
def rest_list_projects():
    return list_projects_data()


@app.get("/api/v1/projects/{project_name}")
def rest_get_project(project_name: str):
    return get_project_data(project_name)


# OpenShift DeploymentConfigs
@app.get("/api/v1/namespaces/{namespace}/deploymentconfigs")
def rest_list_deployment_configs(namespace: str):
    return list_deployment_configs_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/deploymentconfigs/{name}")
def rest_get_deployment_config(namespace: str, name: str):
    return get_deployment_config_data(namespace, name)


@app.post("/api/v1/namespaces/{namespace}/deploymentconfigs/{name}/rollout/restart")
def rest_rollout_restart_deployment_config(namespace: str, name: str):
    return rollout_restart_deployment_config_data(namespace, name)


# OpenShift builds
@app.get("/api/v1/namespaces/{namespace}/buildconfigs")
def rest_list_build_configs(namespace: str):
    return list_build_configs_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/buildconfigs/{name}")
def rest_get_build_config(namespace: str, name: str):
    return get_build_config_data(namespace, name)


@app.get("/api/v1/namespaces/{namespace}/builds")
def rest_list_builds(namespace: str):
    return list_builds_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/builds/{name}")
def rest_get_build(namespace: str, name: str):
    return get_build_data(namespace, name)


# OpenShift image streams
@app.get("/api/v1/namespaces/{namespace}/imagestreams")
def rest_list_image_streams(namespace: str):
    return list_image_streams_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/imagestreams/{name}")
def rest_get_image_stream(namespace: str, name: str):
    return get_image_stream_data(namespace, name)


# OpenShift SCCs / users / groups
@app.get("/api/v1/securitycontextconstraints")
def rest_list_sccs():
    return list_sccs_data()


@app.get("/api/v1/securitycontextconstraints/{name}")
def rest_get_scc(name: str):
    return get_scc_data(name)


@app.get("/api/v1/users")
def rest_list_users():
    return list_users_data()


@app.get("/api/v1/users/{name}")
def rest_get_user(name: str):
    return get_user_data(name)


@app.get("/api/v1/groups")
def rest_list_groups():
    return list_groups_data()


@app.get("/api/v1/groups/{name}")
def rest_get_group(name: str):
    return get_group_data(name)


# OpenShift cluster version / operators
@app.get("/api/v1/clusterversion")
def rest_get_cluster_version():
    return get_cluster_version_data()


@app.get("/api/v1/clusteroperators")
def rest_list_cluster_operators():
    return list_cluster_operators_data()


@app.get("/api/v1/clusteroperators/{name}")
def rest_get_cluster_operator(name: str):
    return get_cluster_operator_data(name)


# Machine Config
@app.get("/api/v1/machineconfigpools")
def rest_list_machine_config_pools():
    return list_machine_config_pools_data()


@app.get("/api/v1/machineconfigpools/{name}")
def rest_get_machine_config_pool(name: str):
    return get_machine_config_pool_data(name)


# Machine API
@app.get("/api/v1/namespaces/{namespace}/machines")
def rest_list_machines(namespace: str):
    return list_machines_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/machinesets")
def rest_list_machine_sets(namespace: str):
    return list_machine_sets_data(namespace)


# OLM
@app.get("/api/v1/namespaces/{namespace}/subscriptions")
def rest_list_subscriptions(namespace: str):
    return list_subscriptions_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/clusterserviceversions")
def rest_list_installed_operators(namespace: str):
    return list_installed_operators_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/catalogsources")
def rest_list_catalog_sources(namespace: str):
    return list_catalog_sources_data(namespace)


# KubeVirt
@app.get("/api/v1/namespaces/{namespace}/virtualmachines")
def rest_list_vms(namespace: str):
    return list_virtualmachines_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}")
def rest_get_vm(namespace: str, vm_name: str):
    return get_virtualmachine_data(namespace, vm_name)


@app.get("/api/v1/namespaces/{namespace}/virtualmachineinstances")
def rest_list_vmis(namespace: str):
    return list_vmis_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/virtualmachineinstances/{vmi_name}")
def rest_get_vmi(namespace: str, vmi_name: str):
    return get_vmi_data(namespace, vmi_name)


@app.put("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/start")
def rest_start_vm(namespace: str, vm_name: str):
    return _vm_power_action(namespace, vm_name, "start")


@app.put("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/stop")
def rest_stop_vm(namespace: str, vm_name: str):
    return _vm_power_action(namespace, vm_name, "stop")


@app.put("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/restart")
def rest_restart_vm(namespace: str, vm_name: str):
    return _vm_power_action(namespace, vm_name, "restart")


@app.put("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/pause")
def rest_pause_vm(namespace: str, vm_name: str):
    return pause_virtualmachine_data(namespace, vm_name)


@app.put("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/unpause")
def rest_unpause_vm(namespace: str, vm_name: str):
    return unpause_virtualmachine_data(namespace, vm_name)


@app.put("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/reboot")
def rest_force_reboot_vm(namespace: str, vm_name: str):
    return force_reboot_virtualmachine_data(namespace, vm_name)


@app.post("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/clone")
def rest_clone_vm(namespace: str, vm_name: str, body: Dict[str, str] = Body(...)):
    new_vm_name = body.get("new_vm_name", f"{vm_name}-clone")
    return clone_virtualmachine_data(namespace, vm_name, new_vm_name)


@app.get("/api/v1/namespaces/{namespace}/virtualmachinesnapshots")
def rest_list_vm_snapshots(namespace: str):
    return list_vm_snapshots_data(namespace)


@app.post("/api/v1/namespaces/{namespace}/virtualmachinesnapshots")
def rest_create_vm_snapshot(namespace: str, body: Dict[str, str] = Body(...)):
    vm_name = body.get("vm_name")
    snapshot_name = body.get("snapshot_name")
    if not vm_name or not snapshot_name:
        raise HTTPException(
            status_code=400, detail="vm_name and snapshot_name required"
        )
    return create_vm_snapshot_data(namespace, vm_name, snapshot_name)


@app.delete("/api/v1/namespaces/{namespace}/virtualmachinesnapshots/{snapshot_name}")
def rest_delete_vm_snapshot(namespace: str, snapshot_name: str):
    return delete_vm_snapshot_data(namespace, snapshot_name)


@app.get("/api/v1/namespaces/{namespace}/datavolumes")
def rest_list_data_volumes(namespace: str):
    return list_data_volumes_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/datavolumes/{dv_name}")
def rest_get_data_volume(namespace: str, dv_name: str):
    return get_data_volume_data(namespace, dv_name)


@app.get("/api/v1/namespaces/{namespace}/virtualmachineinstances/{vmi_name}/console")
def rest_get_vm_console(namespace: str, vmi_name: str):
    return get_vm_console_data(namespace, vmi_name)


@app.get("/api/v1/namespaces/{namespace}/virtualmachinerestores")
def rest_list_vm_restores(namespace: str):
    return list_vm_restores_data(namespace)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
