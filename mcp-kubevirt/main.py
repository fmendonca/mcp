from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field

app = FastAPI(title="Kubernetes/OpenShift MCP Server")

# Load kube config (inside cluster or local)
try:
    config.load_incluster_config()
except config.ConfigException:
    try:
        config.load_kube_config()
    except config.ConfigException:
        raise RuntimeError("Could not configure kubernetes client")

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
batch_v1 = client.BatchV1Api()
rbac_v1 = client.RbacAuthorizationV1Api()
custom_objects = client.CustomObjectsApi()

# Constants
KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
KUBEVIRT_PLURAL = "virtualmachines"

OPENSHIFT_ROUTE_GROUP = "route.openshift.io"
OPENSHIFT_ROUTE_VERSION = "v1"
OPENSHIFT_ROUTE_PLURAL = "routes"


class DeleteOptions(BaseModel):
    grace_period_seconds: Optional[int] = Field(default=None, ge=0)
    force: bool = False


class ResourceRequirementsPatch(BaseModel):
    limits: Optional[Dict[str, str]] = None
    requests: Optional[Dict[str, str]] = None


def api_error(error: ApiException, not_found_detail: str = "Resource not found") -> HTTPException:
    if error.status == 404:
        return HTTPException(status_code=404, detail=not_found_detail)
    if error.status == 403:
        return HTTPException(status_code=403, detail="Forbidden by Kubernetes RBAC")
    return HTTPException(status_code=500, detail=str(error))


def metadata(obj: Any) -> Dict[str, Any]:
    return {
        "name": obj.metadata.name,
        "namespace": obj.metadata.namespace,
        "labels": obj.metadata.labels or {},
        "annotations": obj.metadata.annotations or {},
        "creation_timestamp": obj.metadata.creation_timestamp.isoformat()
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
        "resources": container_resources(container),
    }
    if status:
        data.update(
            {
                "ready": status.ready,
                "restart_count": status.restart_count,
                "state": status.state.to_dict() if status.state else None,
                "last_state": status.last_state.to_dict() if status.last_state else None,
            }
        )
    return data


def summarize_pod(pod: Any) -> Dict[str, Any]:
    statuses = {s.name: s for s in (pod.status.container_statuses or [])}
    return {
        **metadata(pod),
        "phase": pod.status.phase,
        "pod_ip": pod.status.pod_ip,
        "host_ip": pod.status.host_ip,
        "node_name": pod.spec.node_name,
        "restart_policy": pod.spec.restart_policy,
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
    return {
        **metadata(deployment),
        "replicas": deployment.spec.replicas,
        "ready_replicas": deployment.status.ready_replicas or 0,
        "available_replicas": deployment.status.available_replicas or 0,
        "updated_replicas": deployment.status.updated_replicas or 0,
        "strategy": deployment.spec.strategy.to_dict() if deployment.spec.strategy else None,
        "containers": [
            summarize_container(container)
            for container in (deployment.spec.template.spec.containers or [])
        ],
        "conditions": [condition.to_dict() for condition in (deployment.status.conditions or [])],
    }


def summarize_job(job: Any) -> Dict[str, Any]:
    return {
        **metadata(job),
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
        **metadata(cronjob),
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
        **metadata(service),
        "type": service.spec.type,
        "cluster_ip": service.spec.cluster_ip,
        "external_ips": service.spec.external_i_ps or [],
        "ports": [port.to_dict() for port in (service.spec.ports or [])],
        "selector": service.spec.selector or {},
    }


def summarize_event(event: Any) -> Dict[str, Any]:
    event_time = event.event_time or event.last_timestamp or event.first_timestamp
    return {
        **metadata(event),
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
        **metadata(role),
        "rules": [rule.to_dict() for rule in (role.rules or [])],
    }


def summarize_binding(binding: Any) -> Dict[str, Any]:
    return {
        **metadata(binding),
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
        "labels": metadata_obj.get("labels", {}),
        "annotations": metadata_obj.get("annotations", {}),
        "host": spec.get("host"),
        "path": spec.get("path"),
        "to": spec.get("to"),
        "port": spec.get("port"),
        "tls": spec.get("tls"),
        "ingress": status.get("ingress", []),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/namespaces")
def list_namespaces():
    try:
        ns = core_v1.list_namespace()
        return [
            {
                "name": item.metadata.name,
                "status": item.status.phase,
                "labels": item.metadata.labels or {},
                "annotations": item.metadata.annotations or {},
            }
            for item in ns.items
        ]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}")
def get_namespace(namespace: str):
    try:
        ns = core_v1.read_namespace(namespace)
        return {
            **metadata(ns),
            "status": ns.status.phase,
            "conditions": [condition.to_dict() for condition in (ns.status.conditions or [])],
        }
    except ApiException as e:
        raise api_error(e, "Namespace not found")


@app.get("/namespaces/{namespace}/pods")
def list_pods(namespace: str):
    try:
        pods = core_v1.list_namespaced_pod(namespace)
        return [summarize_pod(pod) for pod in pods.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/pods/{pod_name}")
def get_pod(namespace: str, pod_name: str):
    try:
        pod = core_v1.read_namespaced_pod(pod_name, namespace)
        return summarize_pod(pod)
    except ApiException as e:
        raise api_error(e, "Pod not found")


@app.delete("/namespaces/{namespace}/pods/{pod_name}")
def delete_pod(namespace: str, pod_name: str, options: Optional[DeleteOptions] = None):
    try:
        options = options or DeleteOptions()
        grace_period = 0 if options.force else options.grace_period_seconds
        body = client.V1DeleteOptions(grace_period_seconds=grace_period)
        result = core_v1.delete_namespaced_pod(pod_name, namespace, body=body)
        return {
            "status": "delete_requested",
            "name": pod_name,
            "namespace": namespace,
            "result": result.to_dict() if hasattr(result, "to_dict") else result,
        }
    except ApiException as e:
        raise api_error(e, "Pod not found")


@app.get("/namespaces/{namespace}/pods/{pod_name}/logs")
def get_pod_logs(
    namespace: str,
    pod_name: str,
    container: Optional[str] = None,
    tail_lines: int = Query(default=200, ge=1, le=10000),
    since_seconds: Optional[int] = Query(default=None, ge=1),
    previous: bool = False,
):
    try:
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            since_seconds=since_seconds,
            previous=previous,
        )
        return {
            "namespace": namespace,
            "pod": pod_name,
            "container": container,
            "tail_lines": tail_lines,
            "previous": previous,
            "logs": logs,
        }
    except ApiException as e:
        raise api_error(e, "Pod logs not found")


@app.get("/namespaces/{namespace}/pods/{pod_name}/events")
def list_pod_events(namespace: str, pod_name: str):
    try:
        field_selector = f"involvedObject.name={pod_name},involvedObject.kind=Pod"
        events = core_v1.list_namespaced_event(namespace, field_selector=field_selector)
        return [summarize_event(event) for event in events.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/containers")
def list_containers(namespace: str):
    try:
        pods = core_v1.list_namespaced_pod(namespace)
        containers: List[Dict[str, Any]] = []
        for pod in pods.items:
            statuses = {s.name: s for s in (pod.status.container_statuses or [])}
            for container in pod.spec.containers or []:
                containers.append(
                    {
                        "pod": pod.metadata.name,
                        "namespace": namespace,
                        **summarize_container(container, statuses.get(container.name)),
                    }
                )
        return containers
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/events")
def list_events(namespace: str):
    try:
        events = core_v1.list_namespaced_event(namespace)
        return [summarize_event(event) for event in events.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/services")
def list_services(namespace: str):
    try:
        services = core_v1.list_namespaced_service(namespace)
        return [summarize_service(service) for service in services.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/services/{service_name}")
def get_service(namespace: str, service_name: str):
    try:
        service = core_v1.read_namespaced_service(service_name, namespace)
        return summarize_service(service)
    except ApiException as e:
        raise api_error(e, "Service not found")


@app.get("/namespaces/{namespace}/deployments")
def list_deployments(namespace: str):
    try:
        deployments = apps_v1.list_namespaced_deployment(namespace)
        return [summarize_deployment(deployment) for deployment in deployments.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/deployments/{deployment_name}")
def get_deployment(namespace: str, deployment_name: str):
    try:
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        return summarize_deployment(deployment)
    except ApiException as e:
        raise api_error(e, "Deployment not found")


@app.post("/namespaces/{namespace}/deployments/{deployment_name}/rollout/restart")
def rollout_restart_deployment(namespace: str, deployment_name: str):
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


@app.get("/namespaces/{namespace}/deployments/{deployment_name}/rollout/status")
def get_deployment_rollout_status(namespace: str, deployment_name: str):
    try:
        deployment = apps_v1.read_namespaced_deployment_status(deployment_name, namespace)
        desired = deployment.spec.replicas or 0
        updated = deployment.status.updated_replicas or 0
        available = deployment.status.available_replicas or 0
        observed = deployment.status.observed_generation or 0
        generation = deployment.metadata.generation or 0
        complete = observed >= generation and updated == desired and available == desired
        return {
            "name": deployment_name,
            "namespace": namespace,
            "complete": complete,
            "desired_replicas": desired,
            "updated_replicas": updated,
            "available_replicas": available,
            "observed_generation": observed,
            "generation": generation,
            "conditions": [condition.to_dict() for condition in (deployment.status.conditions or [])],
        }
    except ApiException as e:
        raise api_error(e, "Deployment not found")


@app.patch("/namespaces/{namespace}/deployments/{deployment_name}/containers/{container_name}/resources")
def update_deployment_container_resources(
    namespace: str,
    deployment_name: str,
    container_name: str,
    resources: ResourceRequirementsPatch,
):
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


@app.get("/namespaces/{namespace}/jobs")
def list_jobs(namespace: str):
    try:
        jobs = batch_v1.list_namespaced_job(namespace)
        return [summarize_job(job) for job in jobs.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/jobs/{job_name}")
def get_job(namespace: str, job_name: str):
    try:
        job = batch_v1.read_namespaced_job(job_name, namespace)
        return summarize_job(job)
    except ApiException as e:
        raise api_error(e, "Job not found")


@app.get("/namespaces/{namespace}/cronjobs")
def list_cronjobs(namespace: str):
    try:
        cronjobs = batch_v1.list_namespaced_cron_job(namespace)
        return [summarize_cronjob(cronjob) for cronjob in cronjobs.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/cronjobs/{cronjob_name}")
def get_cronjob(namespace: str, cronjob_name: str):
    try:
        cronjob = batch_v1.read_namespaced_cron_job(cronjob_name, namespace)
        return summarize_cronjob(cronjob)
    except ApiException as e:
        raise api_error(e, "CronJob not found")


@app.get("/namespaces/{namespace}/rbac/roles")
def list_roles(namespace: str):
    try:
        roles = rbac_v1.list_namespaced_role(namespace)
        return [summarize_role(role) for role in roles.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/rbac/roles/{role_name}")
def get_role(namespace: str, role_name: str):
    try:
        role = rbac_v1.read_namespaced_role(role_name, namespace)
        return summarize_role(role)
    except ApiException as e:
        raise api_error(e, "Role not found")


@app.get("/namespaces/{namespace}/rbac/rolebindings")
def list_role_bindings(namespace: str):
    try:
        bindings = rbac_v1.list_namespaced_role_binding(namespace)
        return [summarize_binding(binding) for binding in bindings.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/namespaces/{namespace}/rbac/rolebindings/{role_binding_name}")
def get_role_binding(namespace: str, role_binding_name: str):
    try:
        binding = rbac_v1.read_namespaced_role_binding(role_binding_name, namespace)
        return summarize_binding(binding)
    except ApiException as e:
        raise api_error(e, "RoleBinding not found")


@app.get("/rbac/clusterroles")
def list_cluster_roles():
    try:
        roles = rbac_v1.list_cluster_role()
        return [summarize_role(role) for role in roles.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/rbac/clusterroles/{cluster_role_name}")
def get_cluster_role(cluster_role_name: str):
    try:
        role = rbac_v1.read_cluster_role(cluster_role_name)
        return summarize_role(role)
    except ApiException as e:
        raise api_error(e, "ClusterRole not found")


@app.get("/rbac/clusterrolebindings")
def list_cluster_role_bindings():
    try:
        bindings = rbac_v1.list_cluster_role_binding()
        return [summarize_binding(binding) for binding in bindings.items]
    except ApiException as e:
        raise api_error(e)


@app.get("/rbac/clusterrolebindings/{cluster_role_binding_name}")
def get_cluster_role_binding(cluster_role_binding_name: str):
    try:
        binding = rbac_v1.read_cluster_role_binding(cluster_role_binding_name)
        return summarize_binding(binding)
    except ApiException as e:
        raise api_error(e, "ClusterRoleBinding not found")


@app.get("/namespaces/{namespace}/routes")
def list_routes(namespace: str):
    try:
        routes = custom_objects.list_namespaced_custom_object(
            group=OPENSHIFT_ROUTE_GROUP,
            version=OPENSHIFT_ROUTE_VERSION,
            namespace=namespace,
            plural=OPENSHIFT_ROUTE_PLURAL,
        )
        return [summarize_route(route) for route in routes.get("items", [])]
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="OpenShift Route CRD not found")
        raise api_error(e)


@app.get("/namespaces/{namespace}/routes/{route_name}")
def get_route(namespace: str, route_name: str):
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


@app.get("/namespaces/{namespace}/virtualmachines")
def list_virtualmachines(namespace: str):
    try:
        vms = custom_objects.list_namespaced_custom_object(
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural=KUBEVIRT_PLURAL,
        )
        return vms.get("items", [])
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="KubeVirt CRD not found or no VMs")
        raise api_error(e)


@app.get("/namespaces/{namespace}/virtualmachines/{vm_name}")
def get_virtualmachine(namespace: str, vm_name: str):
    try:
        vm = custom_objects.get_namespaced_custom_object(
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural=KUBEVIRT_PLURAL,
            name=vm_name,
        )
        return vm
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="VirtualMachine not found")
        raise api_error(e)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
