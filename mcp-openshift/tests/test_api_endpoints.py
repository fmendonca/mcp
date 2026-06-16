"""Tests for REST API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

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
        assert data["version"] == "0.3.1"


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
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_error_no_sensitive_information(self, client):
        """Test that error responses don't expose sensitive information."""
        response = client.get("/api/v1/nonexistent/resource")
        if response.status_code >= 400:
            data = response.json()
            detail = data.get("detail", "")
            # Should not contain Kubernetes-specific error details
            assert "kubernetes" not in detail.lower() or "not available" in detail.lower()
