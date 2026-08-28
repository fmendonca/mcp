"""REST API route registrations. Each endpoint is a thin wrapper around the
corresponding *_data function, registered on the shared FastAPI `app`
instance created in main.py.
"""

from typing import Dict, Optional

from fastapi import Body, HTTPException, Query

from data_apps import (
    get_cluster_role_binding_data,
    get_cluster_role_data,
    get_cronjob_data,
    get_daemonset_data,
    get_deployment_data,
    get_hpa_data,
    get_ingress_data,
    get_job_data,
    get_role_binding_data,
    get_role_data,
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
from data_deploy import (
    apply_yaml_data,
    create_build_config_data,
    create_build_data,
    deploy_helm_data,
    get_helm_deploy_logs_data,
    start_build_config_data,
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
from main import app
from models import (
    AMQStreamsInstallRequest,
    BuildConfigStartRequest,
    BuildCreateRequest,
    DeleteOptions,
    HelmDeployRequest,
    LogQuery,
    MustGatherRequest,
    NamespaceCreateRequest,
    OLMOperatorInstallRequest,
    OLMSubscriptionCreateRequest,
    OperatorGroupCreateRequest,
    ProjectCreateRequest,
    ResourceRequirementsPatch,
    ScaleRequest,
    YAMLApplyRequest,
)

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


@app.post("/api/v1/namespaces", status_code=201)
def rest_create_namespace(request: NamespaceCreateRequest):
    return create_namespace_data(
        request.name, labels=request.labels, annotations=request.annotations
    )


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


@app.post("/api/v1/projects", status_code=201)
def rest_create_project(request: ProjectCreateRequest):
    return create_project_data(
        request.name,
        display_name=request.display_name,
        description=request.description,
    )


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


@app.post("/api/v1/namespaces/{namespace}/buildconfigs", status_code=201)
def rest_create_build_config(namespace: str, request: BuildCreateRequest):
    return create_build_config_data(namespace, request.manifest)


@app.post(
    "/api/v1/namespaces/{namespace}/buildconfigs/{name}/instantiate", status_code=201
)
def rest_start_build_config(
    namespace: str,
    name: str,
    request: Optional[BuildConfigStartRequest] = Body(default=None),
):
    request = request or BuildConfigStartRequest()
    return start_build_config_data(
        namespace,
        name,
        env=request.env,
        commit=request.commit,
        message=request.message,
    )


@app.post("/api/v1/namespaces/{namespace}/builds", status_code=201)
def rest_create_build(namespace: str, request: BuildCreateRequest):
    return create_build_data(namespace, request.manifest)


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


@app.post("/api/v1/namespaces/{namespace}/operatorgroups", status_code=201)
def rest_create_operator_group(namespace: str, request: OperatorGroupCreateRequest):
    return create_operator_group_data(
        namespace, name=request.name, target_namespaces=request.target_namespaces
    )


@app.post("/api/v1/namespaces/{namespace}/subscriptions", status_code=201)
def rest_create_olm_subscription(namespace: str, request: OLMSubscriptionCreateRequest):
    return create_olm_subscription_data(
        namespace=namespace,
        package_name=request.package_name,
        channel=request.channel,
        source=request.source,
        source_namespace=request.source_namespace,
        install_plan_approval=request.install_plan_approval,
        name=request.name,
        starting_csv=request.starting_csv,
    )


@app.post("/api/v1/operators/amq-streams", status_code=201)
def rest_install_amq_streams_operator(request: AMQStreamsInstallRequest):
    return install_amq_streams_operator_data(
        namespace=request.namespace,
        channel=request.channel,
        source=request.source,
        source_namespace=request.source_namespace,
        install_plan_approval=request.install_plan_approval,
    )


@app.post("/api/v1/operators/install", status_code=201)
def rest_install_olm_operator(request: OLMOperatorInstallRequest):
    return install_olm_operator_data(
        namespace=request.namespace,
        package_name=request.package_name,
        channel=request.channel,
        source=request.source,
        source_namespace=request.source_namespace,
        install_plan_approval=request.install_plan_approval,
        subscription_name=request.subscription_name,
        starting_csv=request.starting_csv,
        create_operator_group=request.create_operator_group,
        operator_group_name=request.operator_group_name,
        target_namespaces=request.target_namespaces,
    )


@app.post("/api/v1/must-gather", status_code=201)
def rest_start_must_gather(request: MustGatherRequest):
    return start_must_gather_data(
        namespace=request.namespace,
        name=request.name,
        image=request.image,
        service_account_name=request.service_account_name,
        timeout_seconds=request.timeout_seconds,
    )


@app.get("/api/v1/namespaces/{namespace}/must-gather/{job_name}/logs")
def rest_get_must_gather_logs(namespace: str, job_name: str):
    return get_must_gather_logs_data(namespace, job_name)


# Deploy operations
@app.post("/api/v1/yaml/apply", status_code=201)
def rest_apply_yaml(request: YAMLApplyRequest):
    return apply_yaml_data(
        request.manifest,
        namespace=request.namespace,
        dry_run=request.dry_run,
        field_manager=request.field_manager,
    )


@app.post("/api/v1/helm/deploy", status_code=201)
def rest_deploy_helm(request: HelmDeployRequest):
    return deploy_helm_data(
        release_name=request.release_name,
        chart=request.chart,
        namespace=request.namespace,
        repo_url=request.repo_url,
        chart_version=request.chart_version,
        values=request.values,
        values_yaml=request.values_yaml,
        create_namespace=request.create_namespace,
        wait=request.wait,
        timeout=request.timeout,
        job_namespace=request.job_namespace,
        job_name=request.job_name,
        image=request.image,
        service_account_name=request.service_account_name,
        ttl_seconds_after_finished=request.ttl_seconds_after_finished,
        active_deadline_seconds=request.active_deadline_seconds,
    )


@app.get("/api/v1/namespaces/{namespace}/helm/{job_name}/logs")
def rest_get_helm_deploy_logs(namespace: str, job_name: str):
    return get_helm_deploy_logs_data(namespace, job_name)


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
