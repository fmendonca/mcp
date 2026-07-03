"""Error-path and remaining-wiring coverage for the data_* modules.

Most data functions wrap their Kubernetes call in
`except ApiException: raise api_error(e)` — the success paths are covered
by the REST tests, but the except lines themselves were not. The
parametrized sweep below drives every one of them by making the underlying
client method raise, and asserts the ApiException is translated into an
HTTPException instead of leaking.
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_apps  # noqa: E402
import data_core  # noqa: E402
import data_kubevirt  # noqa: E402
import data_olm  # noqa: E402
import data_openshift  # noqa: E402
from config import (  # noqa: E402
    apps_v1,
    autoscaling_v2,
    batch_v1,
    core_v1,
    custom_objects,
    networking_v1,
    rbac_v1,
    storage_v1,
)
from models import ResourceRequirementsPatch  # noqa: E402

# (data function, client instance, client method to break, call args)
ERROR_SWEEP_CASES = [
    # data_core
    (data_core.list_namespaces_data, core_v1, "list_namespace", ()),
    (data_core.get_namespace_data, core_v1, "read_namespace", ("ns",)),
    (data_core.create_namespace_data, core_v1, "create_namespace", ("ns",)),
    (data_core.list_nodes_data, core_v1, "list_node", ()),
    (data_core.list_pods_data, core_v1, "list_namespaced_pod", ("ns",)),
    (data_core.delete_pod_data, core_v1, "delete_namespaced_pod", ("ns", "pod")),
    (data_core.list_events_data, core_v1, "list_namespaced_event", ("ns",)),
    (data_core.list_services_data, core_v1, "list_namespaced_service", ("ns",)),
    (data_core.list_persistent_volumes_data, core_v1, "list_persistent_volume", ()),
    (data_core.list_storage_classes_data, storage_v1, "list_storage_class", ()),
    (
        data_core.list_pvcs_data,
        core_v1,
        "list_namespaced_persistent_volume_claim",
        ("ns",),
    ),
    (data_core.list_config_maps_data, core_v1, "list_namespaced_config_map", ("ns",)),
    (
        data_core.list_service_accounts_data,
        core_v1,
        "list_namespaced_service_account",
        ("ns",),
    ),
    (
        data_core.list_resource_quotas_data,
        core_v1,
        "list_namespaced_resource_quota",
        ("ns",),
    ),
    (
        data_core.list_limit_ranges_data,
        core_v1,
        "list_namespaced_limit_range",
        ("ns",),
    ),
    # data_apps
    (data_apps.list_deployments_data, apps_v1, "list_namespaced_deployment", ("ns",)),
    (
        data_apps.rollout_restart_deployment_data,
        apps_v1,
        "patch_namespaced_deployment",
        ("ns", "dep"),
    ),
    (
        data_apps.scale_deployment_data,
        apps_v1,
        "patch_namespaced_deployment",
        ("ns", "dep", 3),
    ),
    (
        data_apps.list_statefulsets_data,
        apps_v1,
        "list_namespaced_stateful_set",
        ("ns",),
    ),
    (
        data_apps.rollout_restart_statefulset_data,
        apps_v1,
        "patch_namespaced_stateful_set",
        ("ns", "ss"),
    ),
    (
        data_apps.scale_statefulset_data,
        apps_v1,
        "patch_namespaced_stateful_set",
        ("ns", "ss", 3),
    ),
    (data_apps.list_daemonsets_data, apps_v1, "list_namespaced_daemon_set", ("ns",)),
    (data_apps.list_replicasets_data, apps_v1, "list_namespaced_replica_set", ("ns",)),
    (
        data_apps.list_hpas_data,
        autoscaling_v2,
        "list_namespaced_horizontal_pod_autoscaler",
        ("ns",),
    ),
    (data_apps.list_ingresses_data, networking_v1, "list_namespaced_ingress", ("ns",)),
    (
        data_apps.list_network_policies_data,
        networking_v1,
        "list_namespaced_network_policy",
        ("ns",),
    ),
    (data_apps.list_jobs_data, batch_v1, "list_namespaced_job", ("ns",)),
    (data_apps.list_cronjobs_data, batch_v1, "list_namespaced_cron_job", ("ns",)),
    (data_apps.list_roles_data, rbac_v1, "list_namespaced_role", ("ns",)),
    (
        data_apps.list_role_bindings_data,
        rbac_v1,
        "list_namespaced_role_binding",
        ("ns",),
    ),
    (data_apps.list_cluster_roles_data, rbac_v1, "list_cluster_role", ()),
    (
        data_apps.list_cluster_role_bindings_data,
        rbac_v1,
        "list_cluster_role_binding",
        (),
    ),
    # data_olm
    (
        data_olm.create_operator_group_data,
        custom_objects,
        "create_namespaced_custom_object",
        ("ns",),
    ),
    (
        data_olm.start_must_gather_data,
        batch_v1,
        "create_namespaced_job",
        (),
    ),
    (
        data_olm.get_must_gather_logs_data,
        core_v1,
        "list_namespaced_pod",
        ("ns", "job"),
    ),
    # data_openshift
    (
        data_openshift.create_project_data,
        custom_objects,
        "create_cluster_custom_object",
        ("proj",),
    ),
    # data_kubevirt
    (
        data_kubevirt.create_vm_snapshot_data,
        custom_objects,
        "create_namespaced_custom_object",
        ("ns", "vm", "snap"),
    ),
]


@pytest.mark.parametrize(
    "func,client_obj,method,args",
    ERROR_SWEEP_CASES,
    ids=[case[0].__name__ for case in ERROR_SWEEP_CASES],
)
def test_api_exception_translated_to_http_exception(func, client_obj, method, args):
    """Every data function converts ApiException into an HTTPException."""
    with patch.object(client_obj, method, side_effect=ApiException(status=500)):
        with pytest.raises(HTTPException) as exc_info:
            func(*args)
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


class TestUpdateDeploymentResourcesBranches:
    """Branch coverage for update_deployment_container_resources_data."""

    def test_requests_only_patch(self, client):
        from kubernetes import client as k8s

        container = k8s.V1Container(name="app", image="nginx:1.0")
        dep = k8s.V1Deployment(
            metadata=k8s.V1ObjectMeta(name="dep", namespace="ns"),
            spec=k8s.V1DeploymentSpec(
                selector=k8s.V1LabelSelector(match_labels={"app": "dep"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(containers=[container])
                ),
            ),
            status=k8s.V1DeploymentStatus(),
        )
        with (
            patch.object(apps_v1, "read_namespaced_deployment", return_value=dep),
            patch.object(
                apps_v1, "patch_namespaced_deployment", return_value=dep
            ) as patch_call,
        ):
            result = data_apps.update_deployment_container_resources_data(
                "ns", "dep", "app", ResourceRequirementsPatch(requests={"cpu": "1"})
            )

        assert result["status"] == "resources_updated"
        body = patch_call.call_args.args[2]
        resources = body["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert resources == {"requests": {"cpu": "1"}}

    def test_neither_limits_nor_requests_rejected(self):
        from kubernetes import client as k8s

        container = k8s.V1Container(name="app", image="nginx:1.0")
        dep = k8s.V1Deployment(
            metadata=k8s.V1ObjectMeta(name="dep", namespace="ns"),
            spec=k8s.V1DeploymentSpec(
                selector=k8s.V1LabelSelector(match_labels={"app": "dep"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(containers=[container])
                ),
            ),
            status=k8s.V1DeploymentStatus(),
        )
        with patch.object(apps_v1, "read_namespaced_deployment", return_value=dep):
            with pytest.raises(HTTPException) as exc_info:
                data_apps.update_deployment_container_resources_data(
                    "ns", "dep", "app", ResourceRequirementsPatch()
                )
        assert exc_info.value.status_code == 400

    def test_api_exception_on_read(self):
        with patch.object(
            apps_v1,
            "read_namespaced_deployment",
            side_effect=ApiException(status=500),
        ):
            with pytest.raises(HTTPException) as exc_info:
                data_apps.update_deployment_container_resources_data(
                    "ns", "dep", "app", ResourceRequirementsPatch(limits={"cpu": "1"})
                )
        assert exc_info.value.status_code == 500


class TestOlmBranches:
    """Branch coverage for the OLM create/subscription helpers."""

    def test_create_subscription_with_starting_csv(self):
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value={"metadata": {"name": "sub"}},
        ) as create_call:
            data_olm.create_olm_subscription_data(
                namespace="ns", package_name="pkg", starting_csv="pkg.v1.2.3"
            )

        body = create_call.call_args.args[4]
        assert body["spec"]["startingCSV"] == "pkg.v1.2.3"

    def test_create_subscription_api_exception(self):
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            side_effect=ApiException(status=409),
        ):
            with pytest.raises(HTTPException) as exc_info:
                data_olm.create_olm_subscription_data(
                    namespace="ns", package_name="pkg"
                )
        assert exc_info.value.status_code == 409


class TestKubevirtErrorBranches:
    """Error branches in KubeVirt clone and force-reboot."""

    def test_clone_create_fails(self):
        with (
            patch.object(
                custom_objects,
                "get_namespaced_custom_object",
                return_value={"metadata": {"name": "vm"}, "spec": {}},
            ),
            patch.object(
                custom_objects,
                "create_namespaced_custom_object",
                side_effect=ApiException(status=500),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                data_kubevirt.clone_virtualmachine_data("ns", "vm", "vm-clone")
        assert exc_info.value.status_code == 500

    def test_force_reboot_api_exception(self):
        with patch.object(
            custom_objects.api_client,
            "call_api",
            side_effect=ApiException(status=500),
        ):
            with pytest.raises(HTTPException) as exc_info:
                data_kubevirt.force_reboot_virtualmachine_data("ns", "vm")
        assert exc_info.value.status_code == 500


class TestOpenshiftGetWiring:
    """REST wiring for the OpenShift get-one endpoints that only had list
    coverage (DeploymentConfig, BuildConfig, Build, ImageStream, SCC, User,
    Group) plus the deployment rollout-status alias.
    """

    def test_get_deployment_config(self, client):
        obj = {"metadata": {"name": "dc", "namespace": "ns"}, "spec": {}, "status": {}}
        with patch.object(
            custom_objects, "get_namespaced_custom_object", return_value=obj
        ):
            response = client.get("/api/v1/namespaces/ns/deploymentconfigs/dc")
        assert response.status_code == 200
        assert response.json()["name"] == "dc"

    def test_get_build_config(self, client):
        obj = {"metadata": {"name": "bc", "namespace": "ns"}, "spec": {}, "status": {}}
        with patch.object(
            custom_objects, "get_namespaced_custom_object", return_value=obj
        ):
            response = client.get("/api/v1/namespaces/ns/buildconfigs/bc")
        assert response.status_code == 200
        assert response.json()["name"] == "bc"

    def test_get_build(self, client):
        obj = {"metadata": {"name": "b-1", "namespace": "ns"}, "status": {}}
        with patch.object(
            custom_objects, "get_namespaced_custom_object", return_value=obj
        ):
            response = client.get("/api/v1/namespaces/ns/builds/b-1")
        assert response.status_code == 200
        assert response.json()["name"] == "b-1"

    def test_get_image_stream(self, client):
        obj = {"metadata": {"name": "is", "namespace": "ns"}, "status": {}, "spec": {}}
        with patch.object(
            custom_objects, "get_namespaced_custom_object", return_value=obj
        ):
            response = client.get("/api/v1/namespaces/ns/imagestreams/is")
        assert response.status_code == 200
        assert response.json()["name"] == "is"

    def test_get_scc(self, client):
        obj = {"metadata": {"name": "restricted"}}
        with patch.object(
            custom_objects, "get_cluster_custom_object", return_value=obj
        ):
            response = client.get("/api/v1/securitycontextconstraints/restricted")
        assert response.status_code == 200
        assert response.json()["name"] == "restricted"

    def test_get_user(self, client):
        obj = {"metadata": {"name": "admin"}}
        with patch.object(
            custom_objects, "get_cluster_custom_object", return_value=obj
        ):
            response = client.get("/api/v1/users/admin")
        assert response.status_code == 200
        assert response.json()["name"] == "admin"

    def test_get_group(self, client):
        obj = {"metadata": {"name": "admins"}}
        with patch.object(
            custom_objects, "get_cluster_custom_object", return_value=obj
        ):
            response = client.get("/api/v1/groups/admins")
        assert response.status_code == 200
        assert response.json()["name"] == "admins"

    def test_deployment_rollout_status_alias(self, client):
        from kubernetes import client as k8s

        dep = k8s.V1Deployment(
            metadata=k8s.V1ObjectMeta(name="dep", namespace="ns"),
            spec=k8s.V1DeploymentSpec(
                replicas=1,
                selector=k8s.V1LabelSelector(match_labels={"app": "dep"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="app", image="nginx")]
                    )
                ),
            ),
            status=k8s.V1DeploymentStatus(),
        )
        with patch.object(apps_v1, "read_namespaced_deployment", return_value=dep):
            response = client.get(
                "/api/v1/namespaces/ns/deployments/dep/rollout/status"
            )
        assert response.status_code == 200
        assert response.json()["name"] == "dep"
