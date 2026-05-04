import contextlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from pydantic import BaseModel, Field

KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
KUBEVIRT_PLURAL = "virtualmachines"

OPENSHIFT_ROUTE_GROUP = "route.openshift.io"
OPENSHIFT_ROUTE_VERSION = "v1"
OPENSHIFT_ROUTE_PLURAL = "routes"


def csv_env(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


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


def configure_kubernetes() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException:
            raise RuntimeError("Could not configure kubernetes client")


configure_kubernetes()

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
batch_v1 = client.BatchV1Api()
rbac_v1 = client.RbacAuthorizationV1Api()
custom_objects = client.CustomObjectsApi()


def api_error(error: ApiException, not_found_detail: str = "Resource not found") -> HTTPException:
    if error.status == 404:
        return HTTPException(status_code=404, detail=not_found_detail)
    if error.status == 403:
        return HTTPException(status_code=403, detail="Forbidden by Kubernetes RBAC")
    if error.status == 401:
        return HTTPException(status_code=401, detail="Kubernetes authentication failed")
    detail = error.reason or error.body or str(error)
    return HTTPException(status_code=500, detail=detail)


def list_response(items: List[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    return {"kind": kind, "count": len(items), "items": items}


def object_metadata(obj: Any) -> Dict[str, Any]:
    return {
        "name": obj.metadata.name,
        "namespace": obj.metadata.namespace,
        "uid": obj.metadata.uid,
        "resource_version": obj.metadata.resource_version,
        "labels": obj.metadata.labels or {},
        "annotations": obj.metadata.annotations or {},
        "created_at": obj.metadata.creation_timestamp.isoformat()
        if obj.metadata.creation_timestamp
        else None,
    }


def container_resources(container: Any) -> Dict[str, Any]:
    resources = container.resources
    if not resources:
        return {"limits": {}, "requests": {}}
    return {
        "limits": resources.limits or {},
        "requests": resources.requests or {},
    }


def summarize_container(container: Any, status: Optional[Any] = None) -> Dict[str, Any]:
    data = {
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
                "last_state": status.last_state.to_dict() if status.last_state else None,
            }
        )
    return data


def summarize_namespace(namespace: Any) -> Dict[str, Any]:
    return {
        **object_metadata(namespace),
        "status": namespace.status.phase,
        "conditions": [condition.to_dict() for condition in (namespace.status.conditions or [])],
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
            summarize_container(container, statuses.get(container.name))
            for container in (pod.spec.containers or [])
        ],
        "init_containers": [
            summarize_container(container)
            for container in (pod.spec.init_containers or [])
        ],
        "conditions": [condition.to_dict() for condition in (pod.status.conditions or [])],
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
        "rollout_complete": observed >= generation and updated == desired and available == desired,
        "observed_generation": observed,
        "generation": generation,
        "strategy": deployment.spec.strategy.to_dict() if deployment.spec.strategy else None,
        "containers": [
            summarize_container(container)
            for container in (deployment.spec.template.spec.containers or [])
        ],
        "conditions": [condition.to_dict() for condition in (deployment.status.conditions or [])],
    }


def summarize_job(job: Any) -> Dict[str, Any]:
    return {
        **object_metadata(job),
        "parallelism": job.spec.parallelism,
        "completions": job.spec.completions,
        "active": job.status.active or 0,
        "succeeded": job.status.succeeded or 0,
        "failed": job.status.failed or 0,
        "start_time": job.status.start_time.isoformat() if job.status.start_time else None,
        "completion_time": job.status.completion_time.isoformat() if job.status.completion_time else None,
        "conditions": [condition.to_dict() for condition in (job.status.conditions or [])],
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
        "last_schedule_time": cronjob.status.last_schedule_time.isoformat()
        if cronjob.status.last_schedule_time
        else None,
        "last_successful_time": cronjob.status.last_successful_time.isoformat()
        if cronjob.status.last_successful_time
        else None,
    }


def summarize_service(service: Any) -> Dict[str, Any]:
    return {
        **object_metadata(service),
        "type": service.spec.type,
        "cluster_ip": service.spec.cluster_ip,
        "external_ips": service.spec.external_i_ps or [],
        "ports": [port.to_dict() for port in (service.spec.ports or [])],
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
        "involved_object": event.involved_object.to_dict()
        if event.involved_object
        else None,
        "event_time": event_time.isoformat() if event_time else None,
    }


def summarize_role(role: Any) -> Dict[str, Any]:
    return {
        **object_metadata(role),
        "rules": [rule.to_dict() for rule in (role.rules or [])],
    }


def summarize_binding(binding: Any) -> Dict[str, Any]:
    return {
        **object_metadata(binding),
        "role_ref": binding.role_ref.to_dict() if binding.role_ref else None,
        "subjects": [subject.to_dict() for subject in (binding.subjects or [])],
    }


def summarize_route(route: Dict[str, Any]) -> Dict[str, Any]:
    spec = route.get("spec", {})
    status = route.get("status", {})
    metadata_obj = route.get("metadata", {})
    return {
        "name": metadata_obj.get("name"),
        "namespace": metadata_obj.get("namespace"),
        "uid": metadata_obj.get("uid"),
        "resource_version": metadata_obj.get("resourceVersion"),
        "labels": metadata_obj.get("labels", {}),
        "annotations": metadata_obj.get("annotations", {}),
        "created_at": metadata_obj.get("creationTimestamp"),
        "host": spec.get("host"),
        "path": spec.get("path"),
        "to": spec.get("to"),
        "port": spec.get("port"),
        "tls": spec.get("tls"),
        "ingress": status.get("ingress", []),
    }


def list_namespaces_data() -> Dict[str, Any]:
    try:
        namespaces = core_v1.list_namespace()
        return list_response([summarize_namespace(item) for item in namespaces.items], "NamespaceList")
    except ApiException as e:
        raise api_error(e)


def get_namespace_data(namespace: str) -> Dict[str, Any]:
    try:
        return summarize_namespace(core_v1.read_namespace(namespace))
    except ApiException as e:
        raise api_error(e, "Namespace not found")


def list_pods_data(namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
    try:
        pods = core_v1.list_namespaced_pod(namespace, label_selector=label_selector)
        return list_response([summarize_pod(pod) for pod in pods.items], "PodList")
    except ApiException as e:
        raise api_error(e)


def get_pod_data(namespace: str, pod_name: str) -> Dict[str, Any]:
    try:
        return summarize_pod(core_v1.read_namespaced_pod(pod_name, namespace))
    except ApiException as e:
        raise api_error(e, "Pod not found")


def delete_pod_data(namespace: str, pod_name: str, options: Optional[DeleteOptions] = None) -> Dict[str, Any]:
    try:
        options = options or DeleteOptions()
        grace_period = 0 if options.force else options.grace_period_seconds
        body = client.V1DeleteOptions(grace_period_seconds=grace_period)
        result = core_v1.delete_namespaced_pod(pod_name, namespace, body=body)
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


def get_pod_logs_data(namespace: str, pod_name: str, query: Optional[LogQuery] = None) -> Dict[str, Any]:
    try:
        query = query or LogQuery()
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
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
        events = core_v1.list_namespaced_event(namespace, field_selector=",".join(selectors) or None)
        return list_response([summarize_event(event) for event in events.items], "EventList")
    except ApiException as e:
        raise api_error(e)


def list_containers_data(namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
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
        services = core_v1.list_namespaced_service(namespace)
        return list_response([summarize_service(service) for service in services.items], "ServiceList")
    except ApiException as e:
        raise api_error(e)


def get_service_data(namespace: str, service_name: str) -> Dict[str, Any]:
    try:
        return summarize_service(core_v1.read_namespaced_service(service_name, namespace))
    except ApiException as e:
        raise api_error(e, "Service not found")


def list_deployments_data(namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
    try:
        deployments = apps_v1.list_namespaced_deployment(namespace, label_selector=label_selector)
        return list_response(
            [summarize_deployment(deployment) for deployment in deployments.items],
            "DeploymentList",
        )
    except ApiException as e:
        raise api_error(e)


def get_deployment_data(namespace: str, deployment_name: str) -> Dict[str, Any]:
    try:
        return summarize_deployment(apps_v1.read_namespaced_deployment(deployment_name, namespace))
    except ApiException as e:
        raise api_error(e, "Deployment not found")


def rollout_restart_deployment_data(namespace: str, deployment_name: str) -> Dict[str, Any]:
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
        apps_v1.patch_namespaced_deployment(deployment_name, namespace, body)
        return {
            "status": "rollout_restart_requested",
            "name": deployment_name,
            "namespace": namespace,
            "restarted_at": restarted_at,
        }
    except ApiException as e:
        raise api_error(e, "Deployment not found")


def get_deployment_rollout_status_data(namespace: str, deployment_name: str) -> Dict[str, Any]:
    return get_deployment_data(namespace, deployment_name)


def update_deployment_container_resources_data(
    namespace: str,
    deployment_name: str,
    container_name: str,
    resources: ResourceRequirementsPatch,
) -> Dict[str, Any]:
    try:
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        containers = deployment.spec.template.spec.containers or []
        if not any(container.name == container_name for container in containers):
            raise HTTPException(status_code=404, detail="Container not found in deployment")

        patch_resources: Dict[str, Dict[str, str]] = {}
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
                            {
                                "name": container_name,
                                "resources": patch_resources,
                            }
                        ]
                    }
                }
            }
        }
        updated = apps_v1.patch_namespaced_deployment(deployment_name, namespace, body)
        matching_container = next(
            container
            for container in updated.spec.template.spec.containers
            if container.name == container_name
        )
        return {
            "status": "resources_updated",
            "deployment": deployment_name,
            "namespace": namespace,
            "container": summarize_container(matching_container),
        }
    except ApiException as e:
        raise api_error(e, "Deployment not found")


def list_jobs_data(namespace: str) -> Dict[str, Any]:
    try:
        jobs = batch_v1.list_namespaced_job(namespace)
        return list_response([summarize_job(job) for job in jobs.items], "JobList")
    except ApiException as e:
        raise api_error(e)


def get_job_data(namespace: str, job_name: str) -> Dict[str, Any]:
    try:
        return summarize_job(batch_v1.read_namespaced_job(job_name, namespace))
    except ApiException as e:
        raise api_error(e, "Job not found")


def list_cronjobs_data(namespace: str) -> Dict[str, Any]:
    try:
        cronjobs = batch_v1.list_namespaced_cron_job(namespace)
        return list_response([summarize_cronjob(cronjob) for cronjob in cronjobs.items], "CronJobList")
    except ApiException as e:
        raise api_error(e)


def get_cronjob_data(namespace: str, cronjob_name: str) -> Dict[str, Any]:
    try:
        return summarize_cronjob(batch_v1.read_namespaced_cron_job(cronjob_name, namespace))
    except ApiException as e:
        raise api_error(e, "CronJob not found")


def list_roles_data(namespace: str) -> Dict[str, Any]:
    try:
        roles = rbac_v1.list_namespaced_role(namespace)
        return list_response([summarize_role(role) for role in roles.items], "RoleList")
    except ApiException as e:
        raise api_error(e)


def get_role_data(namespace: str, role_name: str) -> Dict[str, Any]:
    try:
        return summarize_role(rbac_v1.read_namespaced_role(role_name, namespace))
    except ApiException as e:
        raise api_error(e, "Role not found")


def list_role_bindings_data(namespace: str) -> Dict[str, Any]:
    try:
        bindings = rbac_v1.list_namespaced_role_binding(namespace)
        return list_response([summarize_binding(binding) for binding in bindings.items], "RoleBindingList")
    except ApiException as e:
        raise api_error(e)


def get_role_binding_data(namespace: str, role_binding_name: str) -> Dict[str, Any]:
    try:
        return summarize_binding(rbac_v1.read_namespaced_role_binding(role_binding_name, namespace))
    except ApiException as e:
        raise api_error(e, "RoleBinding not found")


def list_cluster_roles_data() -> Dict[str, Any]:
    try:
        roles = rbac_v1.list_cluster_role()
        return list_response([summarize_role(role) for role in roles.items], "ClusterRoleList")
    except ApiException as e:
        raise api_error(e)


def get_cluster_role_data(cluster_role_name: str) -> Dict[str, Any]:
    try:
        return summarize_role(rbac_v1.read_cluster_role(cluster_role_name))
    except ApiException as e:
        raise api_error(e, "ClusterRole not found")


def list_cluster_role_bindings_data() -> Dict[str, Any]:
    try:
        bindings = rbac_v1.list_cluster_role_binding()
        return list_response(
            [summarize_binding(binding) for binding in bindings.items],
            "ClusterRoleBindingList",
        )
    except ApiException as e:
        raise api_error(e)


def get_cluster_role_binding_data(cluster_role_binding_name: str) -> Dict[str, Any]:
    try:
        return summarize_binding(rbac_v1.read_cluster_role_binding(cluster_role_binding_name))
    except ApiException as e:
        raise api_error(e, "ClusterRoleBinding not found")


def list_routes_data(namespace: str) -> Dict[str, Any]:
    try:
        routes = custom_objects.list_namespaced_custom_object(
            group=OPENSHIFT_ROUTE_GROUP,
            version=OPENSHIFT_ROUTE_VERSION,
            namespace=namespace,
            plural=OPENSHIFT_ROUTE_PLURAL,
        )
        return list_response([summarize_route(route) for route in routes.get("items", [])], "RouteList")
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="OpenShift Route CRD not found")
        raise api_error(e)


def get_route_data(namespace: str, route_name: str) -> Dict[str, Any]:
    try:
        route = custom_objects.get_namespaced_custom_object(
            group=OPENSHIFT_ROUTE_GROUP,
            version=OPENSHIFT_ROUTE_VERSION,
            namespace=namespace,
            plural=OPENSHIFT_ROUTE_PLURAL,
            name=route_name,
        )
        return summarize_route(route)
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Route not found")
        raise api_error(e)


def list_virtualmachines_data(namespace: str) -> Dict[str, Any]:
    try:
        vms = custom_objects.list_namespaced_custom_object(
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural=KUBEVIRT_PLURAL,
        )
        return list_response(vms.get("items", []), "VirtualMachineList")
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="KubeVirt CRD not found")
        raise api_error(e)


def get_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    try:
        return custom_objects.get_namespaced_custom_object(
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural=KUBEVIRT_PLURAL,
            name=vm_name,
        )
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="VirtualMachine not found")
        raise api_error(e)


mcp = FastMCP(
    "OpenShift Kubernetes Operations",
    instructions=(
        "Analyze Kubernetes/OpenShift namespaces, workloads, RBAC, routes, services, "
        "pods, events and logs. Mutating tools can restart deployments, delete pods, "
        "and update deployment container limits/requests."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=csv_env(
            "MCP_ALLOWED_HOSTS",
            ["127.0.0.1:*", "localhost:*", "[::1]:*"],
        ),
        allowed_origins=csv_env(
            "MCP_ALLOWED_ORIGINS",
            ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
        ),
    ),
)


@mcp.tool()
def list_namespaces() -> Dict[str, Any]:
    """List Kubernetes namespaces with labels, annotations, status and conditions."""
    return list_namespaces_data()


@mcp.tool()
def get_namespace(namespace: str) -> Dict[str, Any]:
    """Get details for one Kubernetes namespace."""
    return get_namespace_data(namespace)


@mcp.tool()
def list_pods(namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
    """List pods in a namespace, optionally filtered by a Kubernetes label selector."""
    return list_pods_data(namespace, label_selector)


@mcp.tool()
def get_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get one pod with container status, restart counts, resources and conditions."""
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
    """Delete a pod. Use force=True to set grace_period_seconds to 0."""
    return delete_pod_data(
        namespace,
        pod_name,
        DeleteOptions(grace_period_seconds=grace_period_seconds, force=force),
    )


@mcp.tool()
def list_events(
    namespace: str,
    involved_object_name: Optional[str] = None,
    involved_object_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """List namespace events, optionally filtered by involved object name and kind."""
    return list_events_data(namespace, involved_object_name, involved_object_kind)


@mcp.tool()
def list_containers(namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
    """List containers across pods in a namespace with image, readiness, restarts and resources."""
    return list_containers_data(namespace, label_selector)


@mcp.tool()
def list_services(namespace: str) -> Dict[str, Any]:
    """List services in a namespace."""
    return list_services_data(namespace)


@mcp.tool()
def get_service(namespace: str, service_name: str) -> Dict[str, Any]:
    """Get one service in a namespace."""
    return get_service_data(namespace, service_name)


@mcp.tool()
def list_deployments(namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
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


@mcp.tool()
def list_jobs(namespace: str) -> Dict[str, Any]:
    """List Kubernetes Jobs in a namespace."""
    return list_jobs_data(namespace)


@mcp.tool()
def get_job(namespace: str, job_name: str) -> Dict[str, Any]:
    """Get one Kubernetes Job in a namespace."""
    return get_job_data(namespace, job_name)


@mcp.tool()
def list_cronjobs(namespace: str) -> Dict[str, Any]:
    """List Kubernetes CronJobs in a namespace."""
    return list_cronjobs_data(namespace)


@mcp.tool()
def get_cronjob(namespace: str, cronjob_name: str) -> Dict[str, Any]:
    """Get one Kubernetes CronJob in a namespace."""
    return get_cronjob_data(namespace, cronjob_name)


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


@mcp.tool()
def list_routes(namespace: str) -> Dict[str, Any]:
    """List OpenShift routes in a namespace."""
    return list_routes_data(namespace)


@mcp.tool()
def get_route(namespace: str, route_name: str) -> Dict[str, Any]:
    """Get one OpenShift route in a namespace."""
    return get_route_data(namespace, route_name)


@mcp.tool()
def list_virtualmachines(namespace: str) -> Dict[str, Any]:
    """List KubeVirt VirtualMachines in a namespace."""
    return list_virtualmachines_data(namespace)


@mcp.tool()
def get_virtualmachine(namespace: str, vm_name: str) -> Dict[str, Any]:
    """Get one KubeVirt VirtualMachine in a namespace."""
    return get_virtualmachine_data(namespace, vm_name)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="OpenShift Kubernetes Operations Server",
    version="0.2.1",
    description=(
        "Production REST and MCP server for OpenShift/Kubernetes operational analysis. "
        "Use /api/v1 for REST and /mcp for MCP Streamable HTTP."
    ),
    lifespan=lifespan,
)
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/")
def root():
    return {
        "name": "OpenShift Kubernetes Operations Server",
        "version": app.version,
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
    try:
        core_v1.get_api_resources()
        return {"status": "ready"}
    except ApiException as e:
        raise api_error(e)


@app.get("/api/v1/namespaces")
@app.get("/namespaces", include_in_schema=False)
def rest_list_namespaces():
    return list_namespaces_data()


@app.get("/api/v1/namespaces/{namespace}")
@app.get("/namespaces/{namespace}", include_in_schema=False)
def rest_get_namespace(namespace: str):
    return get_namespace_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/pods")
@app.get("/namespaces/{namespace}/pods", include_in_schema=False)
def rest_list_pods(namespace: str, label_selector: Optional[str] = None):
    return list_pods_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/pods/{pod_name}")
@app.get("/namespaces/{namespace}/pods/{pod_name}", include_in_schema=False)
def rest_get_pod(namespace: str, pod_name: str):
    return get_pod_data(namespace, pod_name)


@app.delete("/api/v1/namespaces/{namespace}/pods/{pod_name}")
@app.delete("/namespaces/{namespace}/pods/{pod_name}", include_in_schema=False)
def rest_delete_pod(
    namespace: str,
    pod_name: str,
    options: Optional[DeleteOptions] = Body(default=None),
):
    return delete_pod_data(namespace, pod_name, options)


@app.get("/api/v1/namespaces/{namespace}/pods/{pod_name}/logs")
@app.get("/namespaces/{namespace}/pods/{pod_name}/logs", include_in_schema=False)
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
@app.get("/namespaces/{namespace}/pods/{pod_name}/events", include_in_schema=False)
def rest_list_pod_events(namespace: str, pod_name: str):
    return list_events_data(namespace, pod_name, "Pod")


@app.get("/api/v1/namespaces/{namespace}/containers")
@app.get("/namespaces/{namespace}/containers", include_in_schema=False)
def rest_list_containers(namespace: str, label_selector: Optional[str] = None):
    return list_containers_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/events")
@app.get("/namespaces/{namespace}/events", include_in_schema=False)
def rest_list_events(
    namespace: str,
    involved_object_name: Optional[str] = None,
    involved_object_kind: Optional[str] = None,
):
    return list_events_data(namespace, involved_object_name, involved_object_kind)


@app.get("/api/v1/namespaces/{namespace}/services")
@app.get("/namespaces/{namespace}/services", include_in_schema=False)
def rest_list_services(namespace: str):
    return list_services_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/services/{service_name}")
@app.get("/namespaces/{namespace}/services/{service_name}", include_in_schema=False)
def rest_get_service(namespace: str, service_name: str):
    return get_service_data(namespace, service_name)


@app.get("/api/v1/namespaces/{namespace}/deployments")
@app.get("/namespaces/{namespace}/deployments", include_in_schema=False)
def rest_list_deployments(namespace: str, label_selector: Optional[str] = None):
    return list_deployments_data(namespace, label_selector)


@app.get("/api/v1/namespaces/{namespace}/deployments/{deployment_name}")
@app.get("/namespaces/{namespace}/deployments/{deployment_name}", include_in_schema=False)
def rest_get_deployment(namespace: str, deployment_name: str):
    return get_deployment_data(namespace, deployment_name)


@app.post("/api/v1/namespaces/{namespace}/deployments/{deployment_name}/rollout/restart")
@app.post("/namespaces/{namespace}/deployments/{deployment_name}/rollout/restart", include_in_schema=False)
def rest_rollout_restart_deployment(namespace: str, deployment_name: str):
    return rollout_restart_deployment_data(namespace, deployment_name)


@app.get("/api/v1/namespaces/{namespace}/deployments/{deployment_name}/rollout/status")
@app.get("/namespaces/{namespace}/deployments/{deployment_name}/rollout/status", include_in_schema=False)
def rest_get_deployment_rollout_status(namespace: str, deployment_name: str):
    return get_deployment_rollout_status_data(namespace, deployment_name)


@app.patch("/api/v1/namespaces/{namespace}/deployments/{deployment_name}/containers/{container_name}/resources")
@app.patch(
    "/namespaces/{namespace}/deployments/{deployment_name}/containers/{container_name}/resources",
    include_in_schema=False,
)
def rest_update_deployment_container_resources(
    namespace: str,
    deployment_name: str,
    container_name: str,
    resources: ResourceRequirementsPatch,
):
    return update_deployment_container_resources_data(namespace, deployment_name, container_name, resources)


@app.get("/api/v1/namespaces/{namespace}/jobs")
@app.get("/namespaces/{namespace}/jobs", include_in_schema=False)
def rest_list_jobs(namespace: str):
    return list_jobs_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/jobs/{job_name}")
@app.get("/namespaces/{namespace}/jobs/{job_name}", include_in_schema=False)
def rest_get_job(namespace: str, job_name: str):
    return get_job_data(namespace, job_name)


@app.get("/api/v1/namespaces/{namespace}/cronjobs")
@app.get("/namespaces/{namespace}/cronjobs", include_in_schema=False)
def rest_list_cronjobs(namespace: str):
    return list_cronjobs_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/cronjobs/{cronjob_name}")
@app.get("/namespaces/{namespace}/cronjobs/{cronjob_name}", include_in_schema=False)
def rest_get_cronjob(namespace: str, cronjob_name: str):
    return get_cronjob_data(namespace, cronjob_name)


@app.get("/api/v1/namespaces/{namespace}/rbac/roles")
@app.get("/namespaces/{namespace}/rbac/roles", include_in_schema=False)
def rest_list_roles(namespace: str):
    return list_roles_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/rbac/roles/{role_name}")
@app.get("/namespaces/{namespace}/rbac/roles/{role_name}", include_in_schema=False)
def rest_get_role(namespace: str, role_name: str):
    return get_role_data(namespace, role_name)


@app.get("/api/v1/namespaces/{namespace}/rbac/rolebindings")
@app.get("/namespaces/{namespace}/rbac/rolebindings", include_in_schema=False)
def rest_list_role_bindings(namespace: str):
    return list_role_bindings_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/rbac/rolebindings/{role_binding_name}")
@app.get("/namespaces/{namespace}/rbac/rolebindings/{role_binding_name}", include_in_schema=False)
def rest_get_role_binding(namespace: str, role_binding_name: str):
    return get_role_binding_data(namespace, role_binding_name)


@app.get("/api/v1/rbac/clusterroles")
@app.get("/rbac/clusterroles", include_in_schema=False)
def rest_list_cluster_roles():
    return list_cluster_roles_data()


@app.get("/api/v1/rbac/clusterroles/{cluster_role_name}")
@app.get("/rbac/clusterroles/{cluster_role_name}", include_in_schema=False)
def rest_get_cluster_role(cluster_role_name: str):
    return get_cluster_role_data(cluster_role_name)


@app.get("/api/v1/rbac/clusterrolebindings")
@app.get("/rbac/clusterrolebindings", include_in_schema=False)
def rest_list_cluster_role_bindings():
    return list_cluster_role_bindings_data()


@app.get("/api/v1/rbac/clusterrolebindings/{cluster_role_binding_name}")
@app.get("/rbac/clusterrolebindings/{cluster_role_binding_name}", include_in_schema=False)
def rest_get_cluster_role_binding(cluster_role_binding_name: str):
    return get_cluster_role_binding_data(cluster_role_binding_name)


@app.get("/api/v1/namespaces/{namespace}/routes")
@app.get("/namespaces/{namespace}/routes", include_in_schema=False)
def rest_list_routes(namespace: str):
    return list_routes_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/routes/{route_name}")
@app.get("/namespaces/{namespace}/routes/{route_name}", include_in_schema=False)
def rest_get_route(namespace: str, route_name: str):
    return get_route_data(namespace, route_name)


@app.get("/api/v1/namespaces/{namespace}/virtualmachines")
@app.get("/namespaces/{namespace}/virtualmachines", include_in_schema=False)
def rest_list_virtualmachines(namespace: str):
    return list_virtualmachines_data(namespace)


@app.get("/api/v1/namespaces/{namespace}/virtualmachines/{vm_name}")
@app.get("/namespaces/{namespace}/virtualmachines/{vm_name}", include_in_schema=False)
def rest_get_virtualmachine(namespace: str, vm_name: str):
    return get_virtualmachine_data(namespace, vm_name)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
