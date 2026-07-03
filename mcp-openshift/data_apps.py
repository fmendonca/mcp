"""Data functions for Kubernetes apps (Deployments, StatefulSets,
DaemonSets, ReplicaSets, HPAs, Ingresses, NetworkPolicies), batch (Jobs,
CronJobs), and RBAC (Roles, RoleBindings, ClusterRoles, ClusterRoleBindings).
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from kubernetes.client.rest import ApiException

from audit import audited
from config import apps_v1, autoscaling_v2, batch_v1, networking_v1, rbac_v1
from errors import api_error
from models import ResourceRequirementsPatch
from summarizers import (
    list_response,
    summarize_binding,
    summarize_container,
    summarize_cronjob,
    summarize_daemonset,
    summarize_deployment,
    summarize_hpa,
    summarize_ingress,
    summarize_job,
    summarize_network_policy,
    summarize_replicaset,
    summarize_role,
    summarize_statefulset,
)
from validation import validated_name


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


@audited("rollout_restart_deployment")
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


@audited("scale_deployment")
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


@audited("update_deployment_container_resources")
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


@audited("rollout_restart_statefulset")
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


@audited("scale_statefulset")
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
