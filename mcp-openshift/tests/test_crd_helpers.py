"""Tests for the generic CRD helpers shared by ~30 OpenShift/OLM/KubeVirt
resource types (_list_namespaced, _get_namespaced, _list_cluster,
_get_cluster) and the generic error mappers (api_error, crd_not_available).
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _get_cluster  # noqa: E402
from main import _get_namespaced  # noqa: E402
from main import _list_cluster  # noqa: E402
from main import _list_namespaced  # noqa: E402
from main import api_error  # noqa: E402
from main import crd_not_available  # noqa: E402
from main import custom_objects  # noqa: E402


def _summarizer(obj):
    return {"name": obj.get("metadata", {}).get("name")}


class TestListNamespaced:
    """Test suite for _list_namespaced."""

    def test_list_namespaced_success(self):
        """Test that a successful list returns a summarized item list."""
        result_obj = {
            "items": [
                {"metadata": {"name": "a"}},
                {"metadata": {"name": "b"}},
            ]
        }
        with patch.object(
            custom_objects, "list_namespaced_custom_object", return_value=result_obj
        ) as list_call:
            result = _list_namespaced(
                "route.openshift.io", "v1", "my-ns", "routes", _summarizer, "RouteList"
            )

        assert result["kind"] == "RouteList"
        assert result["count"] == 2
        assert result["items"] == [{"name": "a"}, {"name": "b"}]
        list_call.assert_called_once_with("route.openshift.io", "v1", "my-ns", "routes")

    def test_list_namespaced_404_means_crd_not_available(self):
        """Test that a 404 on list is treated as 'CRD not installed'."""
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _list_namespaced(
                    "route.openshift.io",
                    "v1",
                    "my-ns",
                    "routes",
                    _summarizer,
                    "RouteList",
                )

        assert exc_info.value.status_code == 404
        assert "not available" in exc_info.value.detail
        assert "CRD not installed" in exc_info.value.detail

    def test_list_namespaced_403_forbidden(self):
        """Test that a 403 is mapped to a forbidden-by-RBAC error."""
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            side_effect=ApiException(status=403),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _list_namespaced(
                    "route.openshift.io",
                    "v1",
                    "my-ns",
                    "routes",
                    _summarizer,
                    "RouteList",
                )

        assert exc_info.value.status_code == 403
        assert "Forbidden" in exc_info.value.detail

    def test_list_namespaced_500_internal_error(self):
        """Test that an unexpected status maps to a generic 500."""
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            side_effect=ApiException(status=418),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _list_namespaced(
                    "route.openshift.io",
                    "v1",
                    "my-ns",
                    "routes",
                    _summarizer,
                    "RouteList",
                )

        assert exc_info.value.status_code == 500


class TestGetNamespaced:
    """Test suite for _get_namespaced."""

    def test_get_namespaced_success(self):
        """Test that a successful get returns the summarized object."""
        obj = {"metadata": {"name": "my-route"}}
        with patch.object(
            custom_objects, "get_namespaced_custom_object", return_value=obj
        ) as get_call:
            result = _get_namespaced(
                "route.openshift.io",
                "v1",
                "my-ns",
                "routes",
                "my-route",
                _summarizer,
                "Route not found",
            )

        assert result == {"name": "my-route"}
        get_call.assert_called_once_with(
            "route.openshift.io", "v1", "my-ns", "routes", "my-route"
        )

    def test_get_namespaced_404_not_found(self):
        """Test that a 404 on get raises the caller-provided not-found message."""
        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _get_namespaced(
                    "route.openshift.io",
                    "v1",
                    "my-ns",
                    "routes",
                    "missing",
                    _summarizer,
                    "Route not found",
                )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Route not found"

    def test_get_namespaced_401_unauthorized(self):
        """Test that a 401 is mapped to a Kubernetes auth failure."""
        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=401),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _get_namespaced(
                    "route.openshift.io",
                    "v1",
                    "my-ns",
                    "routes",
                    "my-route",
                    _summarizer,
                    "Route not found",
                )

        assert exc_info.value.status_code == 401


class TestListCluster:
    """Test suite for _list_cluster."""

    def test_list_cluster_success(self):
        """Test that a successful cluster-scoped list returns summarized items."""
        result_obj = {"items": [{"metadata": {"name": "proj-a"}}]}
        with patch.object(
            custom_objects, "list_cluster_custom_object", return_value=result_obj
        ) as list_call:
            result = _list_cluster(
                "project.openshift.io",
                "v1",
                "projects",
                _summarizer,
                "ProjectList",
            )

        assert result["count"] == 1
        assert result["items"] == [{"name": "proj-a"}]
        list_call.assert_called_once_with("project.openshift.io", "v1", "projects")

    def test_list_cluster_404_means_crd_not_available(self):
        """Test that a 404 on cluster list means the CRD is not installed."""
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            side_effect=ApiException(status=404),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _list_cluster(
                    "project.openshift.io",
                    "v1",
                    "projects",
                    _summarizer,
                    "ProjectList",
                )

        assert exc_info.value.status_code == 404
        assert "not available" in exc_info.value.detail

    def test_list_cluster_409_conflict(self):
        """Test that a 409 is mapped to a resource-already-exists error."""
        with patch.object(
            custom_objects,
            "list_cluster_custom_object",
            side_effect=ApiException(status=409),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _list_cluster(
                    "project.openshift.io",
                    "v1",
                    "projects",
                    _summarizer,
                    "ProjectList",
                )

        assert exc_info.value.status_code == 409


class TestGetCluster:
    """Test suite for _get_cluster."""

    def test_get_cluster_success(self):
        """Test that a successful cluster-scoped get returns the summarized object."""
        obj = {"metadata": {"name": "my-project"}}
        with patch.object(
            custom_objects, "get_cluster_custom_object", return_value=obj
        ) as get_call:
            result = _get_cluster(
                "project.openshift.io",
                "v1",
                "projects",
                "my-project",
                _summarizer,
                "Project not found",
            )

        assert result == {"name": "my-project"}
        get_call.assert_called_once_with(
            "project.openshift.io", "v1", "projects", "my-project"
        )

    def test_get_cluster_404_not_found(self):
        """Test that a 404 on cluster get raises the caller-provided message."""
        with patch.object(
            custom_objects,
            "get_cluster_custom_object",
            side_effect=ApiException(status=404),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _get_cluster(
                    "project.openshift.io",
                    "v1",
                    "projects",
                    "missing",
                    _summarizer,
                    "Project not found",
                )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Project not found"


class TestApiError:
    """Test suite for the generic api_error status-code mapper."""

    def test_api_error_404_uses_custom_detail(self):
        """Test that 404 uses the caller-provided not-found detail."""
        result = api_error(ApiException(status=404), "Widget not found")
        assert result.status_code == 404
        assert result.detail == "Widget not found"

    def test_api_error_403_forbidden(self):
        """Test that 403 is mapped to a forbidden-by-RBAC message."""
        result = api_error(ApiException(status=403))
        assert result.status_code == 403
        assert "Forbidden" in result.detail

    def test_api_error_401_unauthorized(self):
        """Test that 401 is mapped to an authentication-failure message."""
        result = api_error(ApiException(status=401))
        assert result.status_code == 401

    def test_api_error_409_conflict(self):
        """Test that 409 is mapped to a resource-already-exists message."""
        result = api_error(ApiException(status=409))
        assert result.status_code == 409
        assert "already exists" in result.detail

    def test_api_error_unmapped_status_falls_back_to_500(self):
        """Test that unrecognized statuses fall back to a generic 500."""
        result = api_error(ApiException(status=418))
        assert result.status_code == 500
        assert result.detail == "Internal server error"


class TestCrdNotAvailable:
    """Test suite for the crd_not_available helper."""

    def test_crd_not_available_message(self):
        """Test that the message names the resource type and mentions the CRD."""
        result = crd_not_available("VirtualMachineList")
        assert result.status_code == 404
        assert "VirtualMachineList" in result.detail
        assert "CRD not installed" in result.detail
