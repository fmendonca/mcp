"""Wiring sweep for the ~92 pass-through @mcp.tool() wrappers: each
just forwards to a single already-tested *_data function. This confirms
each tool calls the right data function and returns its result
unmodified, catching typos/wrong-function-reference bugs cheaply — the
*_data functions' actual behavior is covered by data_*.py/REST tests.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_tools  # noqa: E402

SIMPLE_TOOL_CASES = [
    ("list_namespaces", "list_namespaces_data", dict()),
    ("get_namespace", "get_namespace_data", dict(namespace="namespace-val")),
    (
        "create_namespace",
        "create_namespace_data",
        dict(namespace="namespace-val", labels=None, annotations=None),
    ),
    ("list_nodes", "list_nodes_data", dict(label_selector=None)),
    ("get_node", "get_node_data", dict(node_name="node_name-val")),
    (
        "list_pods",
        "list_pods_data",
        dict(namespace="namespace-val", label_selector=None),
    ),
    (
        "get_pod",
        "get_pod_data",
        dict(namespace="namespace-val", pod_name="pod_name-val"),
    ),
    (
        "list_containers",
        "list_containers_data",
        dict(namespace="namespace-val", label_selector=None),
    ),
    (
        "list_events",
        "list_events_data",
        dict(
            namespace="namespace-val",
            involved_object_name=None,
            involved_object_kind=None,
        ),
    ),
    ("list_services", "list_services_data", dict(namespace="namespace-val")),
    (
        "get_service",
        "get_service_data",
        dict(namespace="namespace-val", service_name="service_name-val"),
    ),
    (
        "list_deployments",
        "list_deployments_data",
        dict(namespace="namespace-val", label_selector=None),
    ),
    (
        "get_deployment",
        "get_deployment_data",
        dict(namespace="namespace-val", deployment_name="deployment_name-val"),
    ),
    (
        "rollout_restart_deployment",
        "rollout_restart_deployment_data",
        dict(namespace="namespace-val", deployment_name="deployment_name-val"),
    ),
    (
        "list_statefulsets",
        "list_statefulsets_data",
        dict(namespace="namespace-val", label_selector=None),
    ),
    (
        "get_statefulset",
        "get_statefulset_data",
        dict(namespace="namespace-val", statefulset_name="statefulset_name-val"),
    ),
    (
        "rollout_restart_statefulset",
        "rollout_restart_statefulset_data",
        dict(namespace="namespace-val", statefulset_name="statefulset_name-val"),
    ),
    (
        "list_daemonsets",
        "list_daemonsets_data",
        dict(namespace="namespace-val", label_selector=None),
    ),
    (
        "get_daemonset",
        "get_daemonset_data",
        dict(namespace="namespace-val", daemonset_name="daemonset_name-val"),
    ),
    (
        "list_replicasets",
        "list_replicasets_data",
        dict(namespace="namespace-val", label_selector=None),
    ),
    ("list_hpas", "list_hpas_data", dict(namespace="namespace-val")),
    (
        "get_hpa",
        "get_hpa_data",
        dict(namespace="namespace-val", hpa_name="hpa_name-val"),
    ),
    ("list_ingresses", "list_ingresses_data", dict(namespace="namespace-val")),
    (
        "get_ingress",
        "get_ingress_data",
        dict(namespace="namespace-val", ingress_name="ingress_name-val"),
    ),
    (
        "list_network_policies",
        "list_network_policies_data",
        dict(namespace="namespace-val"),
    ),
    ("list_persistent_volumes", "list_persistent_volumes_data", dict()),
    (
        "get_persistent_volume",
        "get_persistent_volume_data",
        dict(pv_name="pv_name-val"),
    ),
    ("list_storage_classes", "list_storage_classes_data", dict()),
    (
        "list_persistent_volume_claims",
        "list_pvcs_data",
        dict(namespace="namespace-val"),
    ),
    (
        "get_persistent_volume_claim",
        "get_pvc_data",
        dict(namespace="namespace-val", pvc_name="pvc_name-val"),
    ),
    ("list_config_maps", "list_config_maps_data", dict(namespace="namespace-val")),
    (
        "get_config_map",
        "get_config_map_data",
        dict(namespace="namespace-val", config_map_name="config_map_name-val"),
    ),
    (
        "list_service_accounts",
        "list_service_accounts_data",
        dict(namespace="namespace-val"),
    ),
    (
        "get_service_account",
        "get_service_account_data",
        dict(
            namespace="namespace-val", service_account_name="service_account_name-val"
        ),
    ),
    (
        "list_resource_quotas",
        "list_resource_quotas_data",
        dict(namespace="namespace-val"),
    ),
    (
        "get_resource_quota",
        "get_resource_quota_data",
        dict(namespace="namespace-val", resource_quota_name="resource_quota_name-val"),
    ),
    ("list_limit_ranges", "list_limit_ranges_data", dict(namespace="namespace-val")),
    ("list_jobs", "list_jobs_data", dict(namespace="namespace-val")),
    (
        "get_job",
        "get_job_data",
        dict(namespace="namespace-val", job_name="job_name-val"),
    ),
    ("list_cronjobs", "list_cronjobs_data", dict(namespace="namespace-val")),
    (
        "get_cronjob",
        "get_cronjob_data",
        dict(namespace="namespace-val", cronjob_name="cronjob_name-val"),
    ),
    ("list_routes", "list_routes_data", dict(namespace="namespace-val")),
    (
        "get_route",
        "get_route_data",
        dict(namespace="namespace-val", route_name="route_name-val"),
    ),
    ("list_projects", "list_projects_data", dict()),
    ("get_project", "get_project_data", dict(project_name="project_name-val")),
    (
        "create_project",
        "create_project_data",
        dict(project_name="project_name-val", display_name=None, description=None),
    ),
    (
        "list_deployment_configs",
        "list_deployment_configs_data",
        dict(namespace="namespace-val"),
    ),
    (
        "get_deployment_config",
        "get_deployment_config_data",
        dict(namespace="namespace-val", dc_name="dc_name-val"),
    ),
    (
        "rollout_restart_deployment_config",
        "rollout_restart_deployment_config_data",
        dict(namespace="namespace-val", dc_name="dc_name-val"),
    ),
    ("list_build_configs", "list_build_configs_data", dict(namespace="namespace-val")),
    (
        "get_build_config",
        "get_build_config_data",
        dict(namespace="namespace-val", build_config_name="build_config_name-val"),
    ),
    ("list_builds", "list_builds_data", dict(namespace="namespace-val")),
    (
        "get_build",
        "get_build_data",
        dict(namespace="namespace-val", build_name="build_name-val"),
    ),
    (
        "start_build_config",
        "start_build_config_data",
        dict(
            namespace="namespace-val",
            build_config_name="build_config_name-val",
            env=None,
            commit=None,
            message=None,
        ),
    ),
    (
        "create_build",
        "create_build_data",
        dict(namespace="namespace-val", manifest={"kind": "Build"}),
    ),
    (
        "create_build_config",
        "create_build_config_data",
        dict(namespace="namespace-val", manifest={"kind": "BuildConfig"}),
    ),
    ("list_image_streams", "list_image_streams_data", dict(namespace="namespace-val")),
    (
        "get_image_stream",
        "get_image_stream_data",
        dict(namespace="namespace-val", image_stream_name="image_stream_name-val"),
    ),
    ("list_security_context_constraints", "list_sccs_data", dict()),
    ("get_security_context_constraint", "get_scc_data", dict(scc_name="scc_name-val")),
    ("list_users", "list_users_data", dict()),
    ("get_user", "get_user_data", dict(user_name="user_name-val")),
    ("list_groups", "list_groups_data", dict()),
    ("get_group", "get_group_data", dict(group_name="group_name-val")),
    ("get_cluster_version", "get_cluster_version_data", dict()),
    ("list_cluster_operators", "list_cluster_operators_data", dict()),
    (
        "get_cluster_operator",
        "get_cluster_operator_data",
        dict(operator_name="operator_name-val"),
    ),
    ("list_machine_config_pools", "list_machine_config_pools_data", dict()),
    (
        "get_machine_config_pool",
        "get_machine_config_pool_data",
        dict(pool_name="pool_name-val"),
    ),
    ("list_machines", "list_machines_data", dict(namespace="namespace-val")),
    ("list_machine_sets", "list_machine_sets_data", dict(namespace="namespace-val")),
    (
        "list_olm_subscriptions",
        "list_subscriptions_data",
        dict(namespace="namespace-val"),
    ),
    (
        "list_installed_operators",
        "list_installed_operators_data",
        dict(namespace="namespace-val"),
    ),
    (
        "list_catalog_sources",
        "list_catalog_sources_data",
        dict(namespace="namespace-val"),
    ),
    (
        "create_operator_group",
        "create_operator_group_data",
        dict(namespace="namespace-val", name="name-val", target_namespaces=None),
    ),
    (
        "create_olm_subscription",
        "create_olm_subscription_data",
        dict(
            namespace="namespace-val",
            package_name="package_name-val",
            channel="channel-val",
            source="source-val",
            source_namespace="source_namespace-val",
            install_plan_approval="install_plan_approval-val",
            name=None,
            starting_csv=None,
        ),
    ),
    (
        "install_amq_streams_operator",
        "install_amq_streams_operator_data",
        dict(
            namespace="namespace-val",
            channel="channel-val",
            source="source-val",
            source_namespace="source_namespace-val",
            install_plan_approval="install_plan_approval-val",
        ),
    ),
    (
        "install_olm_operator",
        "install_olm_operator_data",
        dict(
            namespace="namespace-val",
            package_name="package_name-val",
            channel="channel-val",
            source="source-val",
            source_namespace="source_namespace-val",
            install_plan_approval="install_plan_approval-val",
            subscription_name=None,
            starting_csv=None,
            create_operator_group=False,
            operator_group_name="operator_group_name-val",
            target_namespaces=None,
        ),
    ),
    (
        "start_must_gather",
        "start_must_gather_data",
        dict(
            namespace="namespace-val",
            name=None,
            image=None,
            service_account_name="service_account_name-val",
            timeout_seconds=3,
        ),
    ),
    (
        "get_must_gather_logs",
        "get_must_gather_logs_data",
        dict(namespace="namespace-val", job_name="job_name-val"),
    ),
    (
        "apply_yaml",
        "apply_yaml_data",
        dict(
            manifest="apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test\n",
            namespace=None,
            dry_run=False,
            field_manager="mcp-openshift",
        ),
    ),
    (
        "deploy_helm",
        "deploy_helm_data",
        dict(
            release_name="release_name-val",
            chart="chart-val",
            namespace="namespace-val",
            repo_url=None,
            chart_version=None,
            values=None,
            values_yaml=None,
            create_namespace=True,
            wait=False,
            timeout="10m",
            job_namespace="mcp-server",
            job_name=None,
            image=None,
            service_account_name="mcp-openshift",
        ),
    ),
    (
        "get_helm_deploy_logs",
        "get_helm_deploy_logs_data",
        dict(namespace="namespace-val", job_name="job_name-val"),
    ),
    (
        "list_virtualmachines",
        "list_virtualmachines_data",
        dict(namespace="namespace-val"),
    ),
    (
        "get_virtualmachine",
        "get_virtualmachine_data",
        dict(namespace="namespace-val", vm_name="vm_name-val"),
    ),
    (
        "list_virtual_machine_instances",
        "list_vmis_data",
        dict(namespace="namespace-val"),
    ),
    (
        "get_virtual_machine_instance",
        "get_vmi_data",
        dict(namespace="namespace-val", vmi_name="vmi_name-val"),
    ),
    (
        "pause_virtual_machine",
        "pause_virtualmachine_data",
        dict(namespace="namespace-val", vm_name="vm_name-val"),
    ),
    (
        "unpause_virtual_machine",
        "unpause_virtualmachine_data",
        dict(namespace="namespace-val", vm_name="vm_name-val"),
    ),
    (
        "force_reboot_virtual_machine",
        "force_reboot_virtualmachine_data",
        dict(namespace="namespace-val", vm_name="vm_name-val"),
    ),
    (
        "clone_virtual_machine",
        "clone_virtualmachine_data",
        dict(
            namespace="namespace-val",
            vm_name="vm_name-val",
            new_vm_name="new_vm_name-val",
        ),
    ),
    ("list_vm_snapshots", "list_vm_snapshots_data", dict(namespace="namespace-val")),
    (
        "create_vm_snapshot",
        "create_vm_snapshot_data",
        dict(
            namespace="namespace-val",
            vm_name="vm_name-val",
            snapshot_name="snapshot_name-val",
        ),
    ),
    (
        "delete_vm_snapshot",
        "delete_vm_snapshot_data",
        dict(namespace="namespace-val", snapshot_name="snapshot_name-val"),
    ),
    ("list_data_volumes", "list_data_volumes_data", dict(namespace="namespace-val")),
    (
        "get_data_volume",
        "get_data_volume_data",
        dict(namespace="namespace-val", data_volume_name="data_volume_name-val"),
    ),
    (
        "get_vm_console",
        "get_vm_console_data",
        dict(namespace="namespace-val", vm_name="vm_name-val"),
    ),
    ("list_vm_restores", "list_vm_restores_data", dict(namespace="namespace-val")),
]


@pytest.mark.parametrize("tool_name,data_func_name,kwargs", SIMPLE_TOOL_CASES)
def test_simple_tool_forwards_to_data_function(tool_name, data_func_name, kwargs):
    """Each simple tool calls its one data function once and returns its result."""
    tool = getattr(mcp_tools, tool_name)
    sentinel = {"_sentinel_for": tool_name}
    with patch.object(mcp_tools, data_func_name, return_value=sentinel) as mock_data:
        result = tool(**kwargs)
    assert result is sentinel
    mock_data.assert_called_once()
