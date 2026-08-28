"""Tests for deployment operations: YAML apply, Helm Jobs, and Builds."""

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _RawResponse:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode()


def _meta(name, namespace="my-ns"):
    return {
        "name": name,
        "namespace": namespace,
        "uid": "uid-1",
        "labels": {},
        "annotations": {},
        "creationTimestamp": None,
    }


class TestApplyYaml:
    def test_apply_yaml_uses_server_side_apply(self, client):
        from main import custom_objects

        discovery = {
            "resources": [
                {
                    "name": "configmaps",
                    "kind": "ConfigMap",
                    "namespaced": True,
                    "verbs": ["get", "list", "patch"],
                }
            ]
        }
        applied = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": _meta("app-config"),
        }

        with patch.object(
            custom_objects.api_client,
            "call_api",
            side_effect=[_RawResponse(discovery), _RawResponse(applied)],
        ) as call_api:
            response = client.post(
                "/api/v1/yaml/apply",
                json={
                    "namespace": "my-ns",
                    "manifest": """
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  key: value
""",
                },
            )

        assert response.status_code == 201
        assert response.json()["items"][0]["name"] == "app-config"
        patch_call = call_api.call_args_list[1]
        assert patch_call.args[:2] == (
            "/api/v1/namespaces/my-ns/configmaps/app-config",
            "PATCH",
        )
        assert patch_call.kwargs["header_params"]["Content-Type"] == (
            "application/apply-patch+yaml"
        )

    def test_apply_yaml_rejects_namespaced_object_without_namespace(self, client):
        from main import custom_objects

        discovery = {
            "resources": [
                {"name": "configmaps", "kind": "ConfigMap", "namespaced": True}
            ]
        }
        with patch.object(
            custom_objects.api_client,
            "call_api",
            return_value=_RawResponse(discovery),
        ):
            response = client.post(
                "/api/v1/yaml/apply",
                json={
                    "manifest": "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cm\n"
                },
            )

        assert response.status_code == 400
        assert "namespaced" in response.json()["detail"]


class TestHelmDeploy:
    def test_deploy_helm_creates_runner_job(self, client):
        from kubernetes import client as k8s

        from main import batch_v1

        job = k8s.V1Job(
            metadata=k8s.V1ObjectMeta(name="helm-job", namespace="mcp-server"),
            spec=k8s.V1JobSpec(
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="helm", image="helm-img")],
                        restart_policy="Never",
                    )
                )
            ),
            status=k8s.V1JobStatus(),
        )
        with patch.object(
            batch_v1, "create_namespaced_job", return_value=job
        ) as create_job:
            response = client.post(
                "/api/v1/helm/deploy",
                json={
                    "release_name": "demo",
                    "chart": "bitnami/nginx",
                    "namespace": "demo-ns",
                    "values": {"replicaCount": 1},
                    "image": "helm-img",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["release_name"] == "demo"
        assert data["logs_tool"] == "get_helm_deploy_logs"
        created_job = create_job.call_args.kwargs["body"]
        container = created_job.spec.template.spec.containers[0]
        assert container.name == "helm"
        assert container.image == "helm-img"
        assert "helm upgrade --install demo bitnami/nginx" in container.command[-1]


class TestBuildDeploy:
    def test_start_build_config_posts_build_request(self, client):
        from main import custom_objects

        build = {
            "metadata": _meta("app-1"),
            "status": {"phase": "New"},
            "spec": {},
        }
        with patch.object(
            custom_objects.api_client,
            "call_api",
            return_value=_RawResponse(build),
        ) as call_api:
            response = client.post(
                "/api/v1/namespaces/my-ns/buildconfigs/app/instantiate",
                json={"env": {"FOO": "bar"}},
            )

        assert response.status_code == 201
        assert response.json()["build"]["name"] == "app-1"
        assert call_api.call_args.args[:2] == (
            "/apis/build.openshift.io/v1/namespaces/my-ns/buildconfigs/app/instantiate",
            "POST",
        )
        assert call_api.call_args.kwargs["body"]["env"] == [
            {"name": "FOO", "value": "bar"}
        ]

    def test_create_build_config_requires_build_config_kind(self, client):
        response = client.post(
            "/api/v1/namespaces/my-ns/buildconfigs",
            json={"manifest": {"kind": "Build", "metadata": {"name": "bad"}}},
        )

        assert response.status_code == 400
        assert "BuildConfig" in response.json()["detail"]

    def test_create_build_posts_manifest(self, client):
        from main import custom_objects

        build = {
            "metadata": _meta("manual-build"),
            "status": {"phase": "New"},
            "spec": {},
        }
        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value=build,
        ) as create_call:
            response = client.post(
                "/api/v1/namespaces/my-ns/builds",
                json={
                    "manifest": {
                        "apiVersion": "build.openshift.io/v1",
                        "kind": "Build",
                        "metadata": {"name": "manual-build"},
                        "spec": {},
                    }
                },
            )

        assert response.status_code == 201
        assert response.json()["build"]["name"] == "manual-build"
        assert create_call.call_args.args[:4] == (
            "build.openshift.io",
            "v1",
            "my-ns",
            "builds",
        )
