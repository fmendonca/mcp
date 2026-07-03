"""Covers the last stragglers: small summarizer branches, auth middleware
401, /readyz outcomes, csv_env override, accepted_kwargs **kwargs branch,
and _get_cluster's non-404 error translation.
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from kubernetes import client as k8s
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import summarizers  # noqa: E402
from config import core_v1, custom_objects  # noqa: E402
from crd_helpers import _get_cluster  # noqa: E402
from validation import csv_env  # noqa: E402


class TestSummarizerBranches:
    """Small conditional branches in the summarizers."""

    def test_container_resources_with_limits(self):
        container = k8s.V1Container(
            name="app",
            image="nginx",
            resources=k8s.V1ResourceRequirements(
                limits={"cpu": "1"}, requests={"cpu": "500m"}
            ),
        )
        result = summarizers.container_resources(container)
        assert result == {"limits": {"cpu": "1"}, "requests": {"cpu": "500m"}}

    def test_summarize_container_with_status(self):
        container = k8s.V1Container(name="app", image="nginx")
        status = k8s.V1ContainerStatus(
            name="app",
            image="nginx",
            image_id="img-1",
            container_id="c-1",
            ready=True,
            started=True,
            restart_count=2,
            state=k8s.V1ContainerState(
                running=k8s.V1ContainerStateRunning(started_at=None)
            ),
            last_state=k8s.V1ContainerState(),
        )
        result = summarizers.summarize_container(container, status)
        assert result["ready"] is True
        assert result["restart_count"] == 2

    def test_summarize_pvc_with_requested_storage(self):
        pvc = k8s.V1PersistentVolumeClaim(
            metadata=k8s.V1ObjectMeta(name="pvc", namespace="ns"),
            spec=k8s.V1PersistentVolumeClaimSpec(
                resources=k8s.V1VolumeResourceRequirements(requests={"storage": "5Gi"})
            ),
            status=k8s.V1PersistentVolumeClaimStatus(phase="Bound"),
        )
        result = summarizers.summarize_pvc(pvc)
        assert result["requested_storage"] == "5Gi"

    def test_summarize_ingress_with_load_balancer(self):
        ingress = k8s.V1Ingress(
            metadata=k8s.V1ObjectMeta(name="ing", namespace="ns"),
            spec=k8s.V1IngressSpec(),
            status=k8s.V1IngressStatus(
                load_balancer=k8s.V1IngressLoadBalancerStatus(
                    ingress=[k8s.V1IngressLoadBalancerIngress(ip="10.0.0.9")]
                )
            ),
        )
        result = summarizers.summarize_ingress(ingress)
        assert result["load_balancer"]["ingress"][0]["ip"] == "10.0.0.9"

    def test_summarize_catalog_source_with_poll_interval(self):
        cs = {
            "metadata": {"name": "cat"},
            "spec": {"updateStrategy": {"registryPoll": {"interval": "30m"}}},
            "status": {},
        }
        result = summarizers.summarize_catalog_source(cs)
        assert result["registry_poll_interval"] == "30m"


class TestAuthMiddleware401:
    """The middleware's 401 branch requires a configured token."""

    def test_protected_endpoint_401_when_token_set(self, client):
        with patch.object(main, "AUTH_TOKEN", "configured-secret"):
            response = client.get("/api/v1/namespaces")
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Bearer realm="mcp-openshift"'

    def test_protected_endpoint_passes_with_token(self, client):
        with (
            patch.object(main, "AUTH_TOKEN", "configured-secret"),
            patch.object(
                core_v1,
                "list_namespace",
                return_value=k8s.V1NamespaceList(items=[]),
            ),
        ):
            response = client.get(
                "/api/v1/namespaces",
                headers={"Authorization": "Bearer configured-secret"},
            )
        assert response.status_code == 200


class TestReadyz:
    """/readyz outcomes with a configured/unconfigured cluster."""

    def test_ready_when_cluster_answers(self, client):
        with (
            patch.object(main, "K8S_AVAILABLE", True),
            patch.object(core_v1, "get_api_resources", return_value=None),
        ):
            response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_503_when_client_unconfigured(self, client):
        with patch.object(main, "K8S_AVAILABLE", False):
            response = client.get("/readyz")
        assert response.status_code == 503

    def test_api_error_translated(self, client):
        with (
            patch.object(main, "K8S_AVAILABLE", True),
            patch.object(
                core_v1, "get_api_resources", side_effect=ApiException(status=403)
            ),
        ):
            response = client.get("/readyz")
        assert response.status_code == 403


class TestMiscHelpers:
    """csv_env override branch, accepted_kwargs **kwargs branch,
    _get_cluster non-404 error.
    """

    def test_csv_env_reads_override(self):
        with patch.dict(os.environ, {"SOME_LIST": "a, b , ,c"}):
            assert csv_env("SOME_LIST", ["default"]) == ["a", "b", "c"]

    def test_accepted_kwargs_passes_all_with_var_keyword(self):
        def sink(**kwargs):
            return kwargs

        assert main.accepted_kwargs(sink, {"anything": 1}) == {"anything": 1}

    def test_get_cluster_non_404_error(self):
        with patch.object(
            custom_objects,
            "get_cluster_custom_object",
            side_effect=ApiException(status=403),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _get_cluster("group", "v1", "things", "name", lambda o: o, "not found")
        assert exc_info.value.status_code == 403
