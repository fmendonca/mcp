"""Tests for KubeVirt REST endpoints: VirtualMachines, VMIs, power actions,
clone, snapshots, DataVolumes, console, and restores."""

import os
import sys
from unittest.mock import patch

import pytest
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestVirtualMachines:
    """Test suite for VirtualMachine and VirtualMachineInstance list/get."""

    def test_list_virtualmachines(self, client):
        from main import custom_objects

        vm = {
            "metadata": {"name": "my-vm", "namespace": "my-ns"},
            "spec": {"running": True},
            "status": {"printableStatus": "Running", "ready": True, "created": True},
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [vm]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/virtualmachines")

        assert response.status_code == 200
        assert response.json()["items"][0]["phase"] == "Running"
        assert list_call.call_args.args[:4] == (
            "kubevirt.io",
            "v1",
            "my-ns",
            "virtualmachines",
        )

    def test_get_virtualmachine_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/virtualmachines/missing")

        assert response.status_code == 404

    def test_list_vmis(self, client):
        from main import custom_objects

        vmi = {
            "metadata": {"name": "my-vm", "namespace": "my-ns"},
            "status": {
                "phase": "Running",
                "nodeName": "worker-1",
                "interfaces": [{"ipAddress": "10.0.0.5"}],
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        }
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [vmi]},
        ):
            response = client.get("/api/v1/namespaces/my-ns/virtualmachineinstances")

        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["ip_address"] == "10.0.0.5"
        assert data["items"][0]["ready"] is True

    def test_get_vmi_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get(
                "/api/v1/namespaces/my-ns/virtualmachineinstances/missing"
            )

        assert response.status_code == 404


class TestVmPowerActions:
    """Test suite for start/stop/restart/pause/unpause/reboot power actions."""

    def test_start_vm(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects.api_client, "call_api", return_value=None
        ) as call_api:
            response = client.put(
                "/api/v1/namespaces/my-ns/virtualmachines/my-vm/start"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "vm_start_requested"
        assert "/virtualmachines/my-vm/start" in call_api.call_args.args[0]

    def test_stop_vm(self, client):
        from main import custom_objects

        with patch.object(custom_objects.api_client, "call_api", return_value=None):
            response = client.put("/api/v1/namespaces/my-ns/virtualmachines/my-vm/stop")

        assert response.status_code == 200
        assert response.json()["status"] == "vm_stop_requested"

    def test_restart_vm(self, client):
        from main import custom_objects

        with patch.object(custom_objects.api_client, "call_api", return_value=None):
            response = client.put(
                "/api/v1/namespaces/my-ns/virtualmachines/my-vm/restart"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "vm_restart_requested"

    def test_start_vm_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects.api_client,
            "call_api",
            side_effect=ApiException(status=404),
        ):
            response = client.put(
                "/api/v1/namespaces/my-ns/virtualmachines/missing/start"
            )

        assert response.status_code == 404

    def test_pause_vm(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects.api_client, "call_api", return_value=None
        ) as call_api:
            response = client.put(
                "/api/v1/namespaces/my-ns/virtualmachines/my-vm/pause"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "vm_pause_requested"
        assert "/virtualmachines/my-vm/pause" in call_api.call_args.args[0]

    def test_unpause_vm(self, client):
        from main import custom_objects

        with patch.object(custom_objects.api_client, "call_api", return_value=None):
            response = client.put(
                "/api/v1/namespaces/my-ns/virtualmachines/my-vm/unpause"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "vm_unpause_requested"

    def test_force_reboot_vm(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects.api_client, "call_api", return_value=None
        ) as call_api:
            response = client.put(
                "/api/v1/namespaces/my-ns/virtualmachines/my-vm/reboot"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "force_reboot_requested"
        assert call_api.call_args.kwargs["body"] == {"force": True}


class TestVmClone:
    """Test suite for VM cloning."""

    def test_clone_vm(self, client):
        from main import custom_objects

        source_vm = {
            "metadata": {"name": "my-vm", "namespace": "my-ns"},
            "spec": {"running": False, "template": {}},
            "status": {},
        }
        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            return_value=source_vm,
        ), patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value={"metadata": {"name": "my-vm-clone"}},
        ) as create_call:
            response = client.post(
                "/api/v1/namespaces/my-ns/virtualmachines/my-vm/clone",
                json={"new_vm_name": "my-vm-clone"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "clone_requested"
        assert data["cloned_vm"] == "my-vm-clone"
        created_body = create_call.call_args.args[4]
        assert created_body["metadata"]["name"] == "my-vm-clone"

    def test_clone_vm_source_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.post(
                "/api/v1/namespaces/my-ns/virtualmachines/missing/clone",
                json={"new_vm_name": "clone"},
            )

        assert response.status_code == 404


class TestVmSnapshots:
    """Test suite for VM snapshot create/list/delete."""

    def test_list_vm_snapshots(self, client):
        from main import custom_objects

        snapshot = {"metadata": {"name": "my-snap", "namespace": "my-ns"}}
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [snapshot]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/virtualmachinesnapshots")

        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert list_call.call_args.args[:4] == (
            "kubevirt.io",
            "v1",
            "my-ns",
            "virtualmachinesnapshots",
        )

    def test_create_vm_snapshot(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "create_namespaced_custom_object",
            return_value={"metadata": {"name": "my-snap"}},
        ) as create_call:
            response = client.post(
                "/api/v1/namespaces/my-ns/virtualmachinesnapshots",
                json={"vm_name": "my-vm", "snapshot_name": "my-snap"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "snapshot_requested"
        assert data["snapshot_name"] == "my-snap"
        body = create_call.call_args.args[4]
        assert body["spec"]["source"]["name"] == "my-vm"

    def test_create_vm_snapshot_missing_fields(self, client):
        response = client.post(
            "/api/v1/namespaces/my-ns/virtualmachinesnapshots",
            json={"vm_name": "my-vm"},
        )

        assert response.status_code == 400

    def test_delete_vm_snapshot(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects, "delete_namespaced_custom_object", return_value=None
        ) as delete_call:
            response = client.delete(
                "/api/v1/namespaces/my-ns/virtualmachinesnapshots/my-snap"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "snapshot_deleted"
        delete_call.assert_called_once()

    def test_delete_vm_snapshot_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "delete_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.delete(
                "/api/v1/namespaces/my-ns/virtualmachinesnapshots/missing"
            )

        assert response.status_code == 404


class TestDataVolumes:
    """Test suite for DataVolume list/get."""

    def test_list_data_volumes(self, client):
        from main import custom_objects

        dv = {"metadata": {"name": "my-dv", "namespace": "my-ns"}}
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [dv]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/datavolumes")

        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert list_call.call_args.args[:4] == (
            "cdi.kubevirt.io",
            "v1beta1",
            "my-ns",
            "datavolumes",
        )

    def test_get_data_volume_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/datavolumes/missing")

        assert response.status_code == 404


class TestVmConsoleAndRestores:
    """Test suite for VM console access and VM restore listing."""

    def test_get_vm_console_available(self, client):
        from main import custom_objects

        vmi = {
            "status": {
                "graphics": [{"type": "vnc"}],
                "accessCredentials": None,
            }
        }
        with patch.object(
            custom_objects, "get_namespaced_custom_object", return_value=vmi
        ):
            response = client.get(
                "/api/v1/namespaces/my-ns/virtualmachineinstances/my-vm/console"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["console_available"] is True

    def test_get_vm_console_not_found(self, client):
        from main import custom_objects

        with patch.object(
            custom_objects,
            "get_namespaced_custom_object",
            side_effect=ApiException(status=404),
        ):
            response = client.get(
                "/api/v1/namespaces/my-ns/virtualmachineinstances/missing/console"
            )

        assert response.status_code == 404

    def test_list_vm_restores(self, client):
        from main import custom_objects

        restore = {"metadata": {"name": "my-restore", "namespace": "my-ns"}}
        with patch.object(
            custom_objects,
            "list_namespaced_custom_object",
            return_value={"items": [restore]},
        ) as list_call:
            response = client.get("/api/v1/namespaces/my-ns/virtualmachinerestores")

        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert list_call.call_args.args[:4] == (
            "kubevirt.io",
            "v1",
            "my-ns",
            "virtualmachinerestores",
        )
