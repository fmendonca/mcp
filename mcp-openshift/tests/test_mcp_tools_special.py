"""Tests for the MCP tools that do more than a pure 1:1 forward to a
single *_data function: model construction, inline validation, composite
calls, and the KubeVirt power-action tools that share a private helper.
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_tools  # noqa: E402


class TestGetPodLogs:
    """Test suite for the get_pod_logs tool's LogQuery construction."""

    def test_builds_log_query_from_kwargs(self):
        with patch.object(
            mcp_tools, "get_pod_logs_data", return_value={"logs": "hi"}
        ) as mock_data:
            result = mcp_tools.get_pod_logs(
                "my-ns",
                "my-pod",
                container="app",
                tail_lines=50,
                since_seconds=120,
                previous=True,
            )

        assert result == {"logs": "hi"}
        args = mock_data.call_args.args
        assert args[0] == "my-ns"
        assert args[1] == "my-pod"
        query = args[2]
        assert query.container == "app"
        assert query.tail_lines == 50
        assert query.since_seconds == 120
        assert query.previous is True

    def test_defaults(self):
        with patch.object(
            mcp_tools, "get_pod_logs_data", return_value={"logs": ""}
        ) as mock_data:
            mcp_tools.get_pod_logs("my-ns", "my-pod")

        query = mock_data.call_args.args[2]
        assert query.container is None
        assert query.tail_lines == 200
        assert query.previous is False


class TestDeletePod:
    """Test suite for the delete_pod tool's DeleteOptions construction."""

    def test_builds_delete_options(self):
        with patch.object(
            mcp_tools, "delete_pod_data", return_value={"status": "delete_requested"}
        ) as mock_data:
            result = mcp_tools.delete_pod(
                "my-ns", "my-pod", grace_period_seconds=30, force=True
            )

        assert result == {"status": "delete_requested"}
        args = mock_data.call_args.args
        assert args[0] == "my-ns"
        assert args[1] == "my-pod"
        options = args[2]
        assert options.grace_period_seconds == 30
        assert options.force is True


class TestUpdateDeploymentContainerResources:
    """Test suite for the ResourceRequirementsPatch construction."""

    def test_builds_resource_patch(self):
        with patch.object(
            mcp_tools,
            "update_deployment_container_resources_data",
            return_value={"status": "resources_updated"},
        ) as mock_data:
            result = mcp_tools.update_deployment_container_resources(
                "my-ns",
                "my-dep",
                "app",
                limits={"cpu": "500m"},
                requests={"cpu": "250m"},
            )

        assert result == {"status": "resources_updated"}
        args = mock_data.call_args.args
        assert args[:3] == ("my-ns", "my-dep", "app")
        patch_obj = args[3]
        assert patch_obj.limits == {"cpu": "500m"}
        assert patch_obj.requests == {"cpu": "250m"}


class TestScaleDeployment:
    """Test suite for scale_deployment's inline replica-range validation."""

    def test_scale_within_range(self):
        with patch.object(
            mcp_tools, "scale_deployment_data", return_value={"replicas": 5}
        ) as mock_data:
            result = mcp_tools.scale_deployment("my-ns", "my-dep", 5)

        assert result == {"replicas": 5}
        mock_data.assert_called_once_with("my-ns", "my-dep", 5)

    def test_negative_replicas_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            mcp_tools.scale_deployment("my-ns", "my-dep", -1)
        assert exc_info.value.status_code == 400

    def test_over_max_replicas_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            mcp_tools.scale_deployment("my-ns", "my-dep", 501)
        assert exc_info.value.status_code == 400


class TestScaleStatefulSet:
    """Test suite for scale_statefulset's inline replica-range validation."""

    def test_scale_within_range(self):
        with patch.object(
            mcp_tools, "scale_statefulset_data", return_value={"replicas": 2}
        ) as mock_data:
            result = mcp_tools.scale_statefulset("my-ns", "my-ss", 2)

        assert result == {"replicas": 2}
        mock_data.assert_called_once_with("my-ns", "my-ss", 2)

    def test_negative_replicas_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            mcp_tools.scale_statefulset("my-ns", "my-ss", -1)
        assert exc_info.value.status_code == 400

    def test_over_max_replicas_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            mcp_tools.scale_statefulset("my-ns", "my-ss", 501)
        assert exc_info.value.status_code == 400


class TestListRbac:
    """Test suite for the composite list_rbac tool."""

    def test_combines_roles_and_role_bindings(self):
        with patch.object(
            mcp_tools, "list_roles_data", return_value={"count": 1}
        ) as mock_roles, patch.object(
            mcp_tools, "list_role_bindings_data", return_value={"count": 2}
        ) as mock_bindings:
            result = mcp_tools.list_rbac("my-ns")

        assert result == {"roles": {"count": 1}, "role_bindings": {"count": 2}}
        mock_roles.assert_called_once_with("my-ns")
        mock_bindings.assert_called_once_with("my-ns")


class TestListClusterRbac:
    """Test suite for the composite list_cluster_rbac tool."""

    def test_combines_cluster_roles_and_bindings(self):
        with patch.object(
            mcp_tools, "list_cluster_roles_data", return_value={"count": 3}
        ) as mock_roles, patch.object(
            mcp_tools, "list_cluster_role_bindings_data", return_value={"count": 4}
        ) as mock_bindings:
            result = mcp_tools.list_cluster_rbac()

        assert result == {
            "cluster_roles": {"count": 3},
            "cluster_role_bindings": {"count": 4},
        }
        mock_roles.assert_called_once_with()
        mock_bindings.assert_called_once_with()


class TestVmPowerActionTools:
    """Test suite for the start/stop/restart VM tools sharing _vm_power_action."""

    def test_start_virtual_machine(self):
        with patch.object(
            mcp_tools, "_vm_power_action", return_value={"status": "vm_start_requested"}
        ) as mock_action:
            result = mcp_tools.start_virtual_machine("my-ns", "my-vm")

        assert result == {"status": "vm_start_requested"}
        mock_action.assert_called_once_with("my-ns", "my-vm", "start")

    def test_stop_virtual_machine(self):
        with patch.object(
            mcp_tools, "_vm_power_action", return_value={"status": "vm_stop_requested"}
        ) as mock_action:
            result = mcp_tools.stop_virtual_machine("my-ns", "my-vm")

        assert result == {"status": "vm_stop_requested"}
        mock_action.assert_called_once_with("my-ns", "my-vm", "stop")

    def test_restart_virtual_machine(self):
        with patch.object(
            mcp_tools,
            "_vm_power_action",
            return_value={"status": "vm_restart_requested"},
        ) as mock_action:
            result = mcp_tools.restart_virtual_machine("my-ns", "my-vm")

        assert result == {"status": "vm_restart_requested"}
        mock_action.assert_called_once_with("my-ns", "my-vm", "restart")
