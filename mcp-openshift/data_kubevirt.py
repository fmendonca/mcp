"""Data functions for KubeVirt VirtualMachines and VirtualMachineInstances:
list/get, power actions (start/stop/restart/pause/unpause/reboot), clone,
snapshots, DataVolumes, console access, and restores.
"""

from typing import Any, Dict

from kubernetes.client.rest import ApiException

from audit import audited
from config import (
    KUBEVIRT_GROUP,
    KUBEVIRT_VERSION,
    KUBEVIRT_VM_PLURAL,
    KUBEVIRT_VMI_PLURAL,
    custom_objects,
)
from crd_helpers import _get_namespaced, _list_namespaced
from errors import api_error
from summarizers import summarize_virtualmachine, summarize_vmi
from validation import validated_name


# KubeVirt VMs / VMIs
def list_virtualmachines_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VM_PLURAL,
        summarize_virtualmachine,
        "VirtualMachineList",
    )


def get_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VM_PLURAL,
        vm_name,
        summarize_virtualmachine,
        "VirtualMachine not found",
    )


def list_vmis_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VMI_PLURAL,
        summarize_vmi,
        "VirtualMachineInstanceList",
    )


def get_vmi_data(namespace: str, vmi_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        KUBEVIRT_VMI_PLURAL,
        vmi_name,
        summarize_vmi,
        "VirtualMachineInstance not found",
    )


@audited("vm_power_action")
def _vm_power_action(namespace: str, vm_name: str, action: str) -> Dict[str, Any]:
    path = f"/apis/subresources.kubevirt.io/v1/namespaces/{validated_name(namespace)}/virtualmachines/{validated_name(vm_name)}/{action}"
    try:
        custom_objects.api_client.call_api(
            path,
            "PUT",
            header_params={"Content-Type": "application/json"},
            body={},
            response_types_map={200: "object", 202: "object", 204: "object"},
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _preload_content=False,
        )
    except ApiException as e:
        raise api_error(e, "VirtualMachine not found")
    return {"status": f"vm_{action}_requested", "name": vm_name, "namespace": namespace}


@audited("clone_virtualmachine")
def clone_virtualmachine_data(
    namespace: str, vm_name: str, new_vm_name: str
) -> Dict[str, Any]:
    try:
        vm = get_virtualmachine_data(namespace, vm_name)
        vm_obj = custom_objects.get_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            KUBEVIRT_VM_PLURAL,
            validated_name(vm_name),
        )
        spec = vm_obj.get("spec", {})
        new_spec = {"metadata": {"name": validated_name(new_vm_name)}, "spec": spec}
        result = custom_objects.create_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            KUBEVIRT_VM_PLURAL,
            new_spec,
        )
        return {
            "status": "clone_requested",
            "source_vm": vm_name,
            "cloned_vm": new_vm_name,
            "namespace": namespace,
        }
    except ApiException as e:
        raise api_error(e, "VirtualMachine not found or clone failed")


def pause_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    return _vm_power_action(namespace, vm_name, "pause")


def unpause_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    return _vm_power_action(namespace, vm_name, "unpause")


@audited("force_reboot_virtualmachine")
def force_reboot_virtualmachine_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    path = f"/apis/subresources.kubevirt.io/v1/namespaces/{validated_name(namespace)}/virtualmachines/{validated_name(vm_name)}/reboot"
    body = {"force": True}
    try:
        custom_objects.api_client.call_api(
            path,
            "PUT",
            header_params={"Content-Type": "application/json"},
            body=body,
            response_types_map={200: "object", 202: "object", 204: "object"},
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _preload_content=False,
        )
    except ApiException as e:
        raise api_error(e, "VirtualMachine not found")
    return {"status": "force_reboot_requested", "name": vm_name, "namespace": namespace}


def list_vm_snapshots_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        "virtualmachinesnapshots",
        lambda s: s,
        "VirtualMachineSnapshotList",
    )


@audited("create_vm_snapshot")
def create_vm_snapshot_data(
    namespace: str, vm_name: str, snapshot_name: str
) -> Dict[str, Any]:
    try:
        snapshot_obj = {
            "apiVersion": f"{KUBEVIRT_GROUP}/{KUBEVIRT_VERSION}",
            "kind": "VirtualMachineSnapshot",
            "metadata": {"name": validated_name(snapshot_name)},
            "spec": {
                "source": {"name": validated_name(vm_name), "kind": "VirtualMachine"}
            },
        }
        result = custom_objects.create_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            "virtualmachinesnapshots",
            snapshot_obj,
        )
        return {
            "status": "snapshot_requested",
            "snapshot_name": snapshot_name,
            "vm_name": vm_name,
            "namespace": namespace,
        }
    except ApiException as e:
        raise api_error(e, "Could not create snapshot")


@audited("delete_vm_snapshot")
def delete_vm_snapshot_data(namespace: str, snapshot_name: str) -> Dict[str, Any]:
    try:
        custom_objects.delete_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            "virtualmachinesnapshots",
            validated_name(snapshot_name),
        )
        return {
            "status": "snapshot_deleted",
            "snapshot_name": snapshot_name,
            "namespace": namespace,
        }
    except ApiException as e:
        raise api_error(e, "Snapshot not found")


def list_data_volumes_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        "cdi.kubevirt.io",
        "v1beta1",
        namespace,
        "datavolumes",
        lambda d: d,
        "DataVolumeList",
    )


def get_data_volume_data(namespace: str, dv_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        "cdi.kubevirt.io",
        "v1beta1",
        namespace,
        "datavolumes",
        dv_name,
        lambda d: d,
        "DataVolume not found",
    )


def get_vm_console_data(namespace: str, vm_name: str) -> Dict[str, Any]:
    try:
        vmi = custom_objects.get_namespaced_custom_object(
            KUBEVIRT_GROUP,
            KUBEVIRT_VERSION,
            validated_name(namespace),
            KUBEVIRT_VMI_PLURAL,
            validated_name(vm_name),
        )
        status = vmi.get("status", {})
        graphics = status.get("graphics", [])
        return {
            "vm_name": vm_name,
            "namespace": namespace,
            "console_available": len(graphics) > 0,
            "graphics": graphics,
            "access_credentials": status.get("accessCredentials"),
        }
    except ApiException as e:
        raise api_error(e, "VirtualMachineInstance not found or no console available")


def list_vm_restores_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        KUBEVIRT_GROUP,
        KUBEVIRT_VERSION,
        namespace,
        "virtualmachinerestores",
        lambda r: r,
        "VirtualMachineRestoreList",
    )
