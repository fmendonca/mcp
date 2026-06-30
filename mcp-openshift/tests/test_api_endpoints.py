"""Tests for REST API endpoints."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRootEndpoint:
    """Test suite for root endpoint."""

    def test_root_returns_server_info(self, client):
        """Test that root endpoint returns server information."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "rest" in data
        assert "mcp" in data

    def test_root_contains_correct_version(self, client):
        """Test that root endpoint returns correct version."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "0.0.10"


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_healthz_endpoint(self, client):
        """Test /healthz health check endpoint."""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_endpoint(self, client):
        """Test /health health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_readyz_endpoint(self, client):
        """Test /readyz readiness probe endpoint."""
        response = client.get("/readyz")
        # This might fail if no Kubernetes cluster is available
        # Expected: 200 if ready, 500+ if not
        assert response.status_code in [200, 500, 502, 503]


class TestDocsEndpoint:
    """Test suite for API documentation endpoints."""

    def test_swagger_docs_available(self, client):
        """Test that Swagger documentation is available."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema_available(self, client):
        """Test that OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data or "swagger" in data

    def test_openapi_schema_contains_namespace_and_project_create(self, client):
        """Test that creation endpoints are exposed in OpenAPI."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "post" in paths["/api/v1/namespaces"]
        assert "post" in paths["/api/v1/projects"]


class TestCreateEndpoints:
    """Test suite for creation endpoints."""

    def test_create_namespace_endpoint(self, client):
        """Test namespace creation delegates to the Kubernetes CoreV1 API."""
        from main import core_v1

        namespace_obj = SimpleNamespace(
            metadata=SimpleNamespace(
                name="teste-calo",
                namespace=None,
                uid="uid-123",
                resource_version="1",
                labels={"owner": "codex"},
                annotations={},
                creation_timestamp=None,
            ),
            status=SimpleNamespace(phase="Active", conditions=[]),
        )

        with patch.object(
            core_v1, "create_namespace", return_value=namespace_obj
        ) as create:
            response = client.post(
                "/api/v1/namespaces",
                json={"name": "teste-calo", "labels": {"owner": "codex"}},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["namespace"]["name"] == "teste-calo"
        create.assert_called_once()
        body = create.call_args.kwargs["body"]
        assert body.metadata.name == "teste-calo"
        assert body.metadata.labels == {"owner": "codex"}

    def test_create_project_endpoint(self, client):
        """Test project creation uses the OpenShift ProjectRequest API."""
        from main import custom_objects

        project_obj = {
            "metadata": {
                "name": "teste-calo",
                "uid": "uid-456",
                "labels": {},
                "annotations": {
                    "openshift.io/display-name": "Teste Calo",
                    "openshift.io/description": "Projeto de teste",
                },
                "creationTimestamp": None,
            },
            "status": {"phase": "Active"},
        }

        with patch.object(
            custom_objects, "create_cluster_custom_object", return_value=project_obj
        ) as create:
            response = client.post(
                "/api/v1/projects",
                json={
                    "name": "teste-calo",
                    "display_name": "Teste Calo",
                    "description": "Projeto de teste",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["project"]["name"] == "teste-calo"
        create.assert_called_once()
        assert create.call_args.args[:3] == (
            "project.openshift.io",
            "v1",
            "projectrequests",
        )
        body = create.call_args.args[3]
        assert body["metadata"]["name"] == "teste-calo"
        assert body["displayName"] == "Teste Calo"
        assert body["description"] == "Projeto de teste"

    def test_create_namespace_rejects_invalid_dns_label(self, client):
        """Test namespace creation rejects names Kubernetes would reject."""
        response = client.post("/api/v1/namespaces", json={"name": "teste_calo"})

        assert response.status_code == 400
        assert "DNS label" in response.json()["detail"]

    def test_create_project_rejects_invalid_dns_label(self, client):
        """Test project creation rejects names OpenShift would reject."""
        response = client.post("/api/v1/projects", json={"name": "teste_calo"})

        assert response.status_code == 400
        assert "DNS label" in response.json()["detail"]

    def test_install_olm_operator_endpoint(self, client):
        """Test generic OLM operator installation creates expected resources."""
        from main import custom_objects

        operator_group_obj = {
            "metadata": {
                "name": "app-operators",
                "namespace": "operators-test",
                "uid": "uid-og",
                "labels": {},
                "annotations": {},
                "creationTimestamp": None,
            },
            "spec": {"targetNamespaces": ["operators-test"]},
            "status": {"namespaces": ["operators-test"]},
        }
        subscription_obj = {
            "metadata": {
                "name": "example-operator",
                "namespace": "operators-test",
                "uid": "uid-sub",
                "labels": {},
                "annotations": {},
                "creationTimestamp": None,
            },
            "spec": {
                "name": "example-operator",
                "channel": "stable",
                "source": "redhat-operators",
                "sourceNamespace": "openshift-marketplace",
                "installPlanApproval": "Automatic",
            },
            "status": {"state": "UpgradePending"},
        }

        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            side_effect=[operator_group_obj, subscription_obj],
        ) as create:
            response = client.post(
                "/api/v1/operators/install",
                json={
                    "namespace": "operators-test",
                    "package_name": "example-operator",
                    "create_operator_group": True,
                    "operator_group_name": "app-operators",
                    "target_namespaces": ["operators-test"],
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["operator_group"]["operator_group"]["name"] == "app-operators"
        assert data["subscription"]["package"] == "example-operator"
        assert create.call_count == 2
        assert create.call_args_list[0].args[:4] == (
            "operators.coreos.com",
            "v1",
            "operators-test",
            "operatorgroups",
        )
        assert create.call_args_list[1].args[:4] == (
            "operators.coreos.com",
            "v1alpha1",
            "operators-test",
            "subscriptions",
        )


class TestErrorResponses:
    """Test suite for error response formats."""

    def test_404_response_format(self, client):
        """Test that 404 responses have correct format."""
        response = client.get("/api/v1/namespaces/nonexistent")
        # Will depend on Kubernetes availability
        if response.status_code == 404:
            data = response.json()
            assert "detail" in data

    def test_invalid_resource_name_validation(self, client):
        """Test that invalid resource names are rejected."""
        response = client.get("/api/v1/namespaces/../etc/passwd")
        # URL normalization may strip traversal (404) or validated_name rejects it (400)
        assert response.status_code in [400, 404]

    def test_error_no_sensitive_information(self, client):
        """Test that error responses don't expose sensitive information."""
        response = client.get("/api/v1/nonexistent/resource")
        if response.status_code >= 400:
            data = response.json()
            detail = data.get("detail", "")
            # Should not contain Kubernetes-specific error details
            assert (
                "kubernetes" not in detail.lower() or "not available" in detail.lower()
            )
