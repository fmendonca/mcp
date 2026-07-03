"""Wiring tests for OpenShift/OLM custom-resource REST endpoints. These
resources are all backed by the generic _list_namespaced/_get_namespaced/
_list_cluster/_get_cluster helpers (already unit-tested directly in
test_crd_helpers.py), so these tests focus on confirming each endpoint
wires the right group/version/plural and passes the response through.
"""

import os
import sys
from unittest.mock import patch

import pytest
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from main import configure_kubernetes, is_authorized_request  # noqa: E402


class _FakeRequest:
    """Minimal stand-in for fastapi.Request exposing only .headers."""

    def __init__(self, headers=None):
        self.headers = headers or {}


class TestIsAuthorizedRequest:
    """Test suite for the is_authorized_request auth helper."""

    def test_no_auth_token_configured_allows_all(self):
        with patch.object(main, "AUTH_TOKEN", None):
            assert is_authorized_request(_FakeRequest()) is True

    def test_valid_bearer_token(self):
        with patch.object(main, "AUTH_TOKEN", "secret-token"):
            req = _FakeRequest({"authorization": "Bearer secret-token"})
            assert is_authorized_request(req) is True

    def test_invalid_bearer_token(self):
        with patch.object(main, "AUTH_TOKEN", "secret-token"):
            req = _FakeRequest({"authorization": "Bearer wrong-token"})
            assert is_authorized_request(req) is False

    def test_missing_authorization_header(self):
        with patch.object(main, "AUTH_TOKEN", "secret-token"):
            assert is_authorized_request(_FakeRequest()) is False

    def test_valid_api_key_header(self):
        with patch.object(main, "AUTH_TOKEN", "secret-token"):
            req = _FakeRequest({"x-mcp-api-key": "secret-token"})
            assert is_authorized_request(req) is True

    def test_invalid_api_key_header(self):
        with patch.object(main, "AUTH_TOKEN", "secret-token"):
            req = _FakeRequest({"x-mcp-api-key": "wrong-key"})
            assert is_authorized_request(req) is False

    def test_wrong_scheme_rejected(self):
        with patch.object(main, "AUTH_TOKEN", "secret-token"):
            req = _FakeRequest({"authorization": "Basic secret-token"})
            assert is_authorized_request(req) is False


class TestConfigureKubernetes:
    """Test suite for configure_kubernetes."""

    def test_incluster_config_success(self):
        with patch.object(k8s_config, "load_incluster_config", return_value=None):
            assert configure_kubernetes() is True

    def test_falls_back_to_kube_config(self):
        with (
            patch.object(
                k8s_config,
                "load_incluster_config",
                side_effect=k8s_config.ConfigException("no in-cluster config"),
            ),
            patch.object(k8s_config, "load_kube_config", return_value=None),
        ):
            assert configure_kubernetes() is True

    def test_both_configs_fail(self):
        with (
            patch.object(
                k8s_config,
                "load_incluster_config",
                side_effect=k8s_config.ConfigException("no in-cluster config"),
            ),
            patch.object(
                k8s_config,
                "load_kube_config",
                side_effect=k8s_config.ConfigException("no kube config"),
            ),
        ):
            assert configure_kubernetes() is False


class TestRoutes:
    """Test suite for Route endpoints."""

    def test_list_routes(self, client):
        from main import custom_objects

        route = {
            "metadata": {"name": "my-route", "namespace": "my-ns"},
            "spec": {"host": "example.com", "to": {"name": "my-svc"}},
            "status": {"ingress": []},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [route]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/routes")

        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["host"] == "example.com"
        assert list_call.call_args.args[:4] == (
            "route.openshift.io",
            "v1",
            "my-ns",
            "routes",
        )

    def test_get_route_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/routes/missing")

        assert response.status_code == 404

    def test_list_routes_crd_not_installed(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/routes")

        assert response.status_code == 404
        assert "CRD not installed" in response.json()["detail"]


class TestProjects:
    """Test suite for Project endpoints."""

    def test_list_projects(self, client):
        from main import custom_objects

        project = {
            "metadata": {"name": "my-project", "annotations": {}},
            "status": {"phase": "Active"},
        }
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            return_value={"items": [project]},
        ) as list_call:
            response = client.get("/api/v1/projects")

        assert response.status_code == 200
        assert response.json()["items"][0]["status"] == "Active"
        assert list_call.call_args.args[:3] == (
            "project.openshift.io",
            "v1",
            "projects",
        )

    def test_get_project_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_cluster_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/projects/missing")

        assert response.status_code == 404

    def test_create_project_endpoint(self, client):
        from main import custom_objects

        project_obj = {
            "metadata": {"name": "new-project", "annotations": {}},
            "status": {"phase": "Active"},
        }
        with patch.object(
            custom_objects,
            "create_cluster_custom_object",
            return_value=project_obj,
        ) as create_call:
            response = client.post(
                "/api/v1/projects",
                json={"name": "new-project", "display_name": "New Project"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["project"]["name"] == "new-project"
        assert create_call.call_args.args[:3] == (
            "project.openshift.io",
            "v1",
            "projectrequests",
        )
        body = create_call.call_args.args[3]
        assert body["kind"] == "ProjectRequest"
        assert body["displayName"] == "New Project"

    def test_create_project_rejects_invalid_dns_label(self, client):
        response = client.post("/api/v1/projects", json={"name": "bad_name!"})
        assert response.status_code == 400


class TestDeploymentConfigs:
    """Test suite for DeploymentConfig endpoints."""

    def test_list_deployment_configs(self, client):
        from main import custom_objects

        dc = {
            "metadata": {"name": "my-dc", "namespace": "my-ns"},
            "spec": {"replicas": 2, "template": {"spec": {"containers": []}}},
            "status": {"readyReplicas": 2},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [dc]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/deploymentconfigs")

        assert response.status_code == 200
        assert response.json()["items"][0]["ready_replicas"] == 2
        assert list_call.call_args.args[:4] == (
            "apps.openshift.io",
            "v1",
            "my-ns",
            "deploymentconfigs",
        )

    def test_rollout_restart_deployment_config(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects.api_client, "call_api", return_value=None
        ) as call_api:
            response = client.post(
                "/api/v1/namespaces/my-ns/deploymentconfigs/my-dc/rollout/restart"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "rollout_requested"
        path = call_api.call_args.args[0]
        assert "deploymentconfigs/my-dc/instantiate" in path

    def test_rollout_restart_deployment_config_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects.api_client,
            "call_api",
            side_effect=ApiException(status=404),
        ):
            response = client.post(
                "/api/v1/namespaces/my-ns/deploymentconfigs/missing/rollout/restart"
            )

        assert response.status_code == 404


class TestBuildsAndImageStreams:
    """Test suite for BuildConfig, Build, and ImageStream endpoints."""

    def test_list_build_configs(self, client):
        from main import custom_objects

        bc = {
            "metadata": {"name": "my-bc", "namespace": "my-ns"},
            "spec": {"source": {"type": "Git"}, "strategy": {"type": "Docker"}},
            "status": {"lastVersion": 3},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [bc]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/buildconfigs")

        assert response.status_code == 200
        assert response.json()["items"][0]["last_version"] == 3
        assert list_call.call_args.args[:4] == (
            "build.openshift.io",
            "v1",
            "my-ns",
            "buildconfigs",
        )

    def test_list_builds(self, client):
        from main import custom_objects

        build = {
            "metadata": {"name": "my-build-1", "namespace": "my-ns"},
            "spec": {"strategy": {"type": "Docker"}},
            "status": {"phase": "Complete"},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [build]},
        ):
            response = client.get("/api/v1/namespaces/my-ns/builds")

        assert response.status_code == 200
        assert response.json()["items"][0]["phase"] == "Complete"

    def test_list_image_streams(self, client):
        from main import custom_objects

        image_stream = {
            "metadata": {"name": "my-is", "namespace": "my-ns"},
            "spec": {},
            "status": {"dockerImageRepository": "registry/my-is", "tags": []},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [image_stream]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/imagestreams")

        assert response.status_code == 200
        assert (
            response.json()["items"][0]["docker_image_repository"] == "registry/my-is"
        )
        assert list_call.call_args.args[:4] == (
            "image.openshift.io",
            "v1",
            "my-ns",
            "imagestreams",
        )


class TestSccsUsersGroups:
    """Test suite for SecurityContextConstraints, Users, and Groups."""

    def test_list_sccs(self, client):
        from main import custom_objects

        scc = {
            "metadata": {"name": "restricted"},
            "allowPrivilegedContainer": False,
            "users": [],
            "groups": ["system:authenticated"],
        }
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            return_value={"items": [scc]},
        ) as list_call:
            response = client.get("/api/v1/securitycontextconstraints")

        assert response.status_code == 200
        assert response.json()["items"][0]["groups"] == ["system:authenticated"]
        assert list_call.call_args.args[:3] == (
            "security.openshift.io",
            "v1",
            "securitycontextconstraints",
        )

    def test_list_users(self, client):
        from main import custom_objects

        user = {"metadata": {"name": "admin"}, "fullName": "Admin User"}
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            return_value={"items": [user]},
        ):
            response = client.get("/api/v1/users")

        assert response.status_code == 200
        assert response.json()["items"][0]["full_name"] == "Admin User"

    def test_list_groups(self, client):
        from main import custom_objects

        group = {"metadata": {"name": "cluster-admins"}, "users": ["admin"]}
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            return_value={"items": [group]},
        ):
            response = client.get("/api/v1/groups")

        assert response.status_code == 200
        assert response.json()["items"][0]["users"] == ["admin"]


class TestClusterVersionAndOperators:
    """Test suite for ClusterVersion and ClusterOperator endpoints."""

    def test_get_cluster_version(self, client):
        from main import custom_objects

        cv = {
            "metadata": {"name": "version"},
            "spec": {"channel": "stable-4.18", "clusterID": "abc-123"},
            "status": {"history": [{"state": "Completed", "version": "4.18.1"}]},
        }
        with patch.object(
            custom_objects, "get_cluster_custom_object", return_value=cv
        ) as get_call:
            response = client.get("/api/v1/clusterversion")

        assert response.status_code == 200
        assert response.json()["version"] == "4.18.1"
        assert get_call.call_args.args[:4] == (
            "config.openshift.io",
            "v1",
            "clusterversions",
            "version",
        )

    def test_list_cluster_operators(self, client):
        from main import custom_objects

        co = {
            "metadata": {"name": "kube-apiserver"},
            "status": {
                "conditions": [{"type": "Available", "status": "True"}],
                "versions": [{"name": "operator", "version": "4.18.1"}],
            },
        }
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            return_value={"items": [co]},
        ):
            response = client.get("/api/v1/clusteroperators")

        assert response.status_code == 200
        assert response.json()["items"][0]["available"] is True

    def test_get_cluster_operator_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_cluster_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/clusteroperators/missing")

        assert response.status_code == 404


class TestMachineApi:
    """Test suite for MachineConfigPools, Machines, and MachineSets."""

    def test_list_machine_config_pools(self, client):
        from main import custom_objects

        mcp = {
            "metadata": {"name": "worker"},
            "spec": {"paused": False},
            "status": {"machineCount": 3, "readyMachineCount": 3, "conditions": []},
        }
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            return_value={"items": [mcp]},
        ):
            response = client.get("/api/v1/machineconfigpools")

        assert response.status_code == 200
        assert response.json()["items"][0]["machine_count"] == 3

    def test_get_machine_config_pool_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_cluster_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/machineconfigpools/missing")

        assert response.status_code == 404

    def test_list_machines(self, client):
        from main import custom_objects

        machine = {
            "metadata": {"name": "worker-1"},
            "spec": {},
            "status": {"phase": "Running", "conditions": []},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [machine]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/openshift-machine-api/machines")

        assert response.status_code == 200
        assert response.json()["items"][0]["phase"] == "Running"
        assert list_call.call_args.args[:4] == (
            "machine.openshift.io",
            "v1beta1",
            "openshift-machine-api",
            "machines",
        )

    def test_list_machine_sets(self, client):
        from main import custom_objects

        machine_set = {
            "metadata": {"name": "worker-set"},
            "spec": {"replicas": 3},
            "status": {"readyReplicas": 3},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [machine_set]},
        ):
            response = client.get(
                "/api/v1/namespaces/openshift-machine-api/machinesets"
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["replicas"] == 3


class TestOlmResources:
    """Test suite for OLM Subscriptions, installed operators, and catalog sources."""

    def test_list_subscriptions(self, client):
        from main import custom_objects

        sub = {
            "metadata": {"name": "my-operator", "namespace": "openshift-operators"},
            "spec": {"name": "my-operator", "channel": "stable"},
            "status": {"state": "AtLatestKnown"},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [sub]},
        ) as list_call:
            response = client.get(
                "/api/v1/namespaces/openshift-operators/subscriptions"
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["state"] == "AtLatestKnown"
        assert list_call.call_args.args[:4] == (
            "operators.coreos.com",
            "v1alpha1",
            "openshift-operators",
            "subscriptions",
        )

    def test_list_installed_operators(self, client):
        from main import custom_objects

        csv = {
            "metadata": {"name": "my-operator.v1.0.0"},
            "spec": {"displayName": "My Operator", "version": "1.0.0"},
            "status": {"phase": "Succeeded"},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [csv]},
        ):
            response = client.get(
                "/api/v1/namespaces/openshift-operators/clusterserviceversions"
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["phase"] == "Succeeded"

    def test_list_catalog_sources(self, client):
        from main import custom_objects

        catalog_source = {
            "metadata": {
                "name": "redhat-operators",
                "namespace": "openshift-marketplace",
            },
            "spec": {"sourceType": "grpc", "displayName": "Red Hat Operators"},
            "status": {"connectionState": {"lastObservedState": "READY"}},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [catalog_source]},
        ):
            response = client.get(
                "/api/v1/namespaces/openshift-marketplace/catalogsources"
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["last_observed_state"] == "READY"

    def test_create_operator_group_endpoint(self, client):
        from main import custom_objects

        og_obj = {
            "metadata": {"name": "mcp-operator-group", "namespace": "operators-ns"},
            "spec": {"targetNamespaces": ["operators-ns"]},
            "status": {},
        }
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value=og_obj,
        ) as create_call:
            response = client.post(
                "/api/v1/namespaces/operators-ns/operatorgroups",
                json={"target_namespaces": ["operators-ns"]},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["operator_group"]["target_namespaces"] == ["operators-ns"]
        assert create_call.call_args.args[:4] == (
            "operators.coreos.com",
            "v1",
            "operators-ns",
            "operatorgroups",
        )

    def test_create_operator_group_rejects_invalid_target_namespace(self, client):
        response = client.post(
            "/api/v1/namespaces/operators-ns/operatorgroups",
            json={"target_namespaces": ["bad_ns!"]},
        )
        assert response.status_code == 400

    def test_create_olm_subscription_endpoint(self, client):
        from main import custom_objects

        sub_obj = {
            "metadata": {"name": "my-operator", "namespace": "operators-ns"},
            "spec": {"name": "my-operator", "channel": "stable"},
            "status": {},
        }
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value=sub_obj,
        ) as create_call:
            response = client.post(
                "/api/v1/namespaces/operators-ns/subscriptions",
                json={"package_name": "my-operator"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["subscription"]["package"] == "my-operator"
        assert create_call.call_args.args[:4] == (
            "operators.coreos.com",
            "v1alpha1",
            "operators-ns",
            "subscriptions",
        )

    def test_install_amq_streams_operator(self, client):
        from main import custom_objects

        sub_obj = {
            "metadata": {"name": "amq-streams", "namespace": "openshift-operators"},
            "spec": {"name": "amq-streams", "channel": "stable"},
            "status": {},
        }
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value=sub_obj,
        ) as create_call:
            response = client.post("/api/v1/operators/amq-streams", json={})

        assert response.status_code == 201
        data = response.json()
        assert data["subscription"]["package"] == "amq-streams"
        body = create_call.call_args.args[4]
        assert body["spec"]["name"] == "amq-streams"

    def test_install_olm_operator_requires_package_name(self, client):
        response = client.post("/api/v1/operators/install", json={"package_name": ""})
        assert response.status_code == 400
        assert "package_name is required" in response.json()["detail"]

    def test_install_olm_operator_without_operator_group(self, client):
        from main import custom_objects

        sub_obj = {
            "metadata": {
                "name": "example-operator",
                "namespace": "openshift-operators",
            },
            "spec": {"name": "example-operator", "channel": "stable"},
            "status": {},
        }
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value=sub_obj,
        ) as create_call:
            response = client.post(
                "/api/v1/operators/install",
                json={"package_name": "example-operator"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["operator_group"] is None
        assert data["subscription"]["package"] == "example-operator"
        create_call.assert_called_once()

    def test_install_olm_operator_with_operator_group(self, client):
        from main import custom_objects

        operator_group_obj = {
            "metadata": {"name": "app-operators", "namespace": "operators-test"},
            "spec": {"targetNamespaces": ["operators-test"]},
            "status": {},
        }
        subscription_obj = {
            "metadata": {"name": "example-operator", "namespace": "operators-test"},
            "spec": {"name": "example-operator", "channel": "stable"},
            "status": {},
        }
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            side_effect=[operator_group_obj, subscription_obj],
        ) as create_call:
            response = client.post(
                "/api/v1/operators/install",
                json={
                    "namespace": "operators-test",
                    "package_name": "example-operator",
                    "create_operator_group": True,
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["operator_group"]["operator_group"]["name"] == "app-operators"
        assert data["subscription"]["package"] == "example-operator"
        assert create_call.call_count == 2


class TestStartMustGather:
    """Test suite for the must-gather job creation endpoint."""

    def test_start_must_gather(self, client):
        from kubernetes import client as k8s

        from main import batch_v1

        job = k8s.V1Job(
            metadata=k8s.V1ObjectMeta(name="mcp-must-gather-1", namespace="mcp-server"),
            spec=k8s.V1JobSpec(
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="must-gather", image="img")],
                        restart_policy="Never",
                    )
                )
            ),
            status=k8s.V1JobStatus(),
        )
        with patch.object(
            batch_v1, "create_namespaced_job", return_value=job
        ) as create_call:
            response = client.post("/api/v1/must-gather", json={})

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["logs_tool"] == "get_must_gather_logs"
        create_call.assert_called_once()

    def test_start_must_gather_rejects_invalid_namespace(self, client):
        response = client.post("/api/v1/must-gather", json={"namespace": "bad_ns!"})
        assert response.status_code == 400


class TestMustGatherLogs:
    """Test suite for must-gather log retrieval."""

    def test_get_must_gather_logs_no_pods(self, client):
        from kubernetes import client as k8s

        from main import core_v1

        with patch.object(
            core_v1,
            "list_namespaced_pod",
            return_value=k8s.V1PodList(items=[]),
        ):
            response = client.get(
                "/api/v1/namespaces/mcp-server/must-gather/my-job/logs"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["pods"] == []
        assert data["logs"] == ""

    def test_get_must_gather_logs_with_pod(self, client):
        from kubernetes import client as k8s

        from main import core_v1

        pod = k8s.V1Pod(metadata=k8s.V1ObjectMeta(name="my-job-abcde"))
        with (
            patch.object(
                core_v1, "list_namespaced_pod", return_value=k8s.V1PodList(items=[pod])
            ),
            patch.object(
                core_v1, "read_namespaced_pod_log", return_value="gathering logs..."
            ),
        ):
            response = client.get(
                "/api/v1/namespaces/mcp-server/must-gather/my-job/logs"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["pod_name"] == "my-job-abcde"
        assert data["logs"] == "gathering logs..."
