"""MCP tool registrations. Each tool is a thin wrapper around the
corresponding *_data function, decorated with @mcp.tool() so FastMCP can
expose it (including its docstring, used as the tool description shown to
MCP clients) over the Streamable HTTP transport.
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from data_apps import (
    get_cronjob_data,
    get_daemonset_data,
    get_deployment_data,
    get_hpa_data,
    get_ingress_data,
    get_job_data,
    get_statefulset_data,
    list_cluster_role_bindings_data,
    list_cluster_roles_data,
    list_cronjobs_data,
    list_daemonsets_data,
    list_deployments_data,
    list_hpas_data,
    list_ingresses_data,
    list_jobs_data,
    list_network_policies_data,
    list_replicasets_data,
    list_role_bindings_data,
    list_roles_data,
    list_statefulsets_data,
    rollout_restart_deployment_data,
    rollout_restart_statefulset_data,
    scale_deployment_data,
    scale_statefulset_data,
    update_deployment_container_resources_data,
)
from data_core import (
    create_namespace_data,
    delete_pod_data,
    get_config_map_data,
    get_namespace_data,
    get_node_data,
    get_persistent_volume_data,
    get_pod_data,
    get_pod_logs_data,
    get_pvc_data,
    get_resource_quota_data,
    get_service_account_data,
    get_service_data,
    list_config_maps_data,
    list_containers_data,
    list_events_data,
    list_limit_ranges_data,
    list_namespaces_data,
    list_nodes_data,
    list_persistent_volumes_data,
    list_pods_data,
    list_pvcs_data,
    list_resource_quotas_data,
    list_service_accounts_data,
    list_services_data,
    list_storage_classes_data,
)
from data_kubevirt import (
    _vm_power_action,
    clone_virtualmachine_data,
    create_vm_snapshot_data,
    delete_vm_snapshot_data,
    force_reboot_virtualmachine_data,
    get_data_volume_data,
    get_virtualmachine_data,
    get_vm_console_data,
    get_vmi_data,
    list_data_volumes_data,
    list_virtualmachines_data,
    list_vm_restores_data,
    list_vm_snapshots_data,
    list_vmis_data,
    pause_virtualmachine_data,
    unpause_virtualmachine_data,
)
from data_olm import (
    create_olm_subscription_data,
    create_operator_group_data,
    get_must_gather_logs_data,
    install_amq_streams_operator_data,
    install_olm_operator_data,
    list_catalog_sources_data,
    list_installed_operators_data,
    list_subscriptions_data,
    start_must_gather_data,
)
from data_openshift import (
    create_project_data,
    get_build_config_data,
    get_build_data,
    get_cluster_operator_data,
    get_cluster_version_data,
    get_deployment_config_data,
    get_group_data,
    get_image_stream_data,
    get_machine_config_pool_data,
    get_project_data,
    get_route_data,
    get_scc_data,
    get_user_data,
    list_build_configs_data,
    list_builds_data,
    list_cluster_operators_data,
    list_deployment_configs_data,
    list_groups_data,
    list_image_streams_data,
    list_machine_config_pools_data,
    list_machine_sets_data,
    list_machines_data,
    list_projects_data,
    list_routes_data,
    list_sccs_data,
    list_users_data,
    rollout_restart_deployment_config_data,
)
from main import mcp
from models import DeleteOptions, LogQuery, ResourceRequirementsPatch


# --- MCP tools: namespaces ---
@mcp.tool()
def list_namespaces() -> Dict[str, Any]:
    """List all Kubernetes namespaces with status, labels and annotations."""
    return list_namespaces_data()


@mcp.tool()
def get_namespace(namespace: str) -> Dict[str, Any]:
    """Get details for one Kubernetes namespace."""
    return get_namespace_data(namespace)


@mcp.tool()
def create_namespace(
    namespace: str,
    labels: Optional[Dict[str, str]] = None,
    annotations: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Create a Kubernetes namespace with optional labels and annotations."""
    return create_namespace_data(namespace, labels=labels, annotations=annotations)


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


@mcp.tool()
def create_project(
    project_name: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an OpenShift Project using a ProjectRequest."""
    return create_project_data(
        project_name, display_name=display_name, description=description
    )


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


@mcp.tool()
def create_operator_group(
    namespace: str,
    name: str = "mcp-operator-group",
    target_namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create an OLM OperatorGroup in a namespace."""
    return create_operator_group_data(namespace, name, target_namespaces)


@mcp.tool()
def create_olm_subscription(
    namespace: str,
    package_name: str,
    channel: str = "stable",
    source: str = "redhat-operators",
    source_namespace: str = "openshift-marketplace",
    install_plan_approval: str = "Automatic",
    name: Optional[str] = None,
    starting_csv: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an OLM Subscription for an operator package."""
    return create_olm_subscription_data(
        namespace=namespace,
        package_name=package_name,
        channel=channel,
        source=source,
        source_namespace=source_namespace,
        install_plan_approval=install_plan_approval,
        name=name,
        starting_csv=starting_csv,
    )


@mcp.tool()
def install_amq_streams_operator(
    namespace: str = "openshift-operators",
    channel: str = "stable",
    source: str = "redhat-operators",
    source_namespace: str = "openshift-marketplace",
    install_plan_approval: str = "Automatic",
) -> Dict[str, Any]:
    """Install Red Hat AMQ Streams through OLM."""
    return install_amq_streams_operator_data(
        namespace=namespace,
        channel=channel,
        source=source,
        source_namespace=source_namespace,
        install_plan_approval=install_plan_approval,
    )


@mcp.tool()
def install_olm_operator(
    namespace: str,
    package_name: str,
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
    """Install any OLM operator package through a Subscription."""
    return install_olm_operator_data(
        namespace=namespace,
        package_name=package_name,
        channel=channel,
        source=source,
        source_namespace=source_namespace,
        install_plan_approval=install_plan_approval,
        subscription_name=subscription_name,
        starting_csv=starting_csv,
        create_operator_group=create_operator_group,
        operator_group_name=operator_group_name,
        target_namespaces=target_namespaces,
    )


@mcp.tool()
def start_must_gather(
    namespace: str = "mcp-server",
    name: Optional[str] = None,
    image: Optional[str] = None,
    service_account_name: str = "mcp-openshift",
    timeout_seconds: int = 3600,
) -> Dict[str, Any]:
    """Start an OpenShift must-gather Job from the MCP server namespace."""
    return start_must_gather_data(
        namespace=namespace,
        name=name,
        image=image,
        service_account_name=service_account_name,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def get_must_gather_logs(namespace: str, job_name: str) -> Dict[str, Any]:
    """Read logs from a must-gather Job started by start_must_gather."""
    return get_must_gather_logs_data(namespace, job_name)


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
