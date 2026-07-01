"""Data functions for core Kubernetes resources: namespaces, nodes, pods,
events, containers, services, storage (PVs/PVCs/StorageClasses), configmaps,
service accounts, resource quotas, and limit ranges.
"""

from typing import Any, Dict, Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

from config import core_v1, storage_v1
from errors import api_error
from models import DeleteOptions, LogQuery
from summarizers import (
    list_response,
    summarize_config_map,
    summarize_event,
    summarize_limit_range,
    summarize_namespace,
    summarize_node,
    summarize_persistent_volume,
    summarize_pod,
    summarize_pvc,
    summarize_resource_quota,
    summarize_service,
    summarize_service_account,
    summarize_storage_class,
)
from validation import validated_dns_label, validated_name


def list_namespaces_data() -> Dict[str, Any]:
    try:
        ns = core_v1.list_namespace()
        return list_response(
            [summarize_namespace(n) for n in ns.items], "NamespaceList"
        )
    except ApiException as e:
        raise api_error(e)


def get_namespace_data(namespace: str) -> Dict[str, Any]:
    try:
        return summarize_namespace(core_v1.read_namespace(validated_name(namespace)))
    except ApiException as e:
        raise api_error(e, "Namespace not found")


def create_namespace_data(
    namespace: str,
    labels: Optional[Dict[str, str]] = None,
    annotations: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    try:
        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=validated_dns_label(namespace, "namespace"),
                labels=labels or {},
                annotations=annotations or {},
            )
        )
        result = core_v1.create_namespace(body=body)
        return {"status": "created", "namespace": summarize_namespace(result)}
    except ApiException as e:
        raise api_error(e)


def list_nodes_data(label_selector: Optional[str] = None) -> Dict[str, Any]:
    try:
        nodes = core_v1.list_node(label_selector=label_selector)
        return list_response([summarize_node(n) for n in nodes.items], "NodeList")
    except ApiException as e:
        raise api_error(e)


def get_node_data(node_name: str) -> Dict[str, Any]:
    try:
        return summarize_node(core_v1.read_node(validated_name(node_name)))
    except ApiException as e:
        raise api_error(e, "Node not found")


def list_pods_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    try:
        pods = core_v1.list_namespaced_pod(
            validated_name(namespace), label_selector=label_selector
        )
        return list_response([summarize_pod(p) for p in pods.items], "PodList")
    except ApiException as e:
        raise api_error(e)


def get_pod_data(namespace: str, pod_name: str) -> Dict[str, Any]:
    try:
        return summarize_pod(
            core_v1.read_namespaced_pod(
                validated_name(pod_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Pod not found")


def delete_pod_data(
    namespace: str, pod_name: str, options: Optional[DeleteOptions] = None
) -> Dict[str, Any]:
    try:
        options = options or DeleteOptions()
        grace_period = 0 if options.force else options.grace_period_seconds
        body = client.V1DeleteOptions(grace_period_seconds=grace_period)
        result = core_v1.delete_namespaced_pod(
            validated_name(pod_name), validated_name(namespace), body=body
        )
        return {
            "status": "delete_requested",
            "name": pod_name,
            "namespace": namespace,
            "force": options.force,
            "grace_period_seconds": grace_period,
            "result": result.to_dict() if hasattr(result, "to_dict") else result,
        }
    except ApiException as e:
        raise api_error(e, "Pod not found")


def get_pod_logs_data(
    namespace: str, pod_name: str, query: Optional[LogQuery] = None
) -> Dict[str, Any]:
    try:
        query = query or LogQuery()
        logs = core_v1.read_namespaced_pod_log(
            name=validated_name(pod_name),
            namespace=validated_name(namespace),
            container=query.container,
            tail_lines=query.tail_lines,
            since_seconds=query.since_seconds,
            previous=query.previous,
        )
        return {
            "namespace": namespace,
            "pod": pod_name,
            "container": query.container,
            "tail_lines": query.tail_lines,
            "since_seconds": query.since_seconds,
            "previous": query.previous,
            "logs": logs,
        }
    except ApiException as e:
        raise api_error(e, "Pod logs not found")


def list_events_data(
    namespace: str,
    involved_object_name: Optional[str] = None,
    involved_object_kind: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        selectors = []
        if involved_object_name:
            selectors.append(f"involvedObject.name={involved_object_name}")
        if involved_object_kind:
            selectors.append(f"involvedObject.kind={involved_object_kind}")
        events = core_v1.list_namespaced_event(
            validated_name(namespace), field_selector=",".join(selectors) or None
        )
        return list_response([summarize_event(e) for e in events.items], "EventList")
    except ApiException as e:
        raise api_error(e)


def list_containers_data(
    namespace: str, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    pods = list_pods_data(namespace, label_selector=label_selector)["items"]
    containers = []
    for pod in pods:
        for container in pod["containers"]:
            containers.append(
                {
                    "namespace": namespace,
                    "pod": pod["name"],
                    "pod_phase": pod["phase"],
                    **container,
                }
            )
    return list_response(containers, "ContainerList")


def list_services_data(namespace: str) -> Dict[str, Any]:
    try:
        svcs = core_v1.list_namespaced_service(validated_name(namespace))
        return list_response([summarize_service(s) for s in svcs.items], "ServiceList")
    except ApiException as e:
        raise api_error(e)


def get_service_data(namespace: str, service_name: str) -> Dict[str, Any]:
    try:
        return summarize_service(
            core_v1.read_namespaced_service(
                validated_name(service_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "Service not found")


def list_persistent_volumes_data() -> Dict[str, Any]:
    try:
        pvs = core_v1.list_persistent_volume()
        return list_response(
            [summarize_persistent_volume(p) for p in pvs.items], "PersistentVolumeList"
        )
    except ApiException as e:
        raise api_error(e)


def get_persistent_volume_data(pv_name: str) -> Dict[str, Any]:
    try:
        return summarize_persistent_volume(
            core_v1.read_persistent_volume(validated_name(pv_name))
        )
    except ApiException as e:
        raise api_error(e, "PersistentVolume not found")


def list_storage_classes_data() -> Dict[str, Any]:
    try:
        scs = storage_v1.list_storage_class()
        return list_response(
            [summarize_storage_class(s) for s in scs.items], "StorageClassList"
        )
    except ApiException as e:
        raise api_error(e)


def list_pvcs_data(namespace: str) -> Dict[str, Any]:
    try:
        pvcs = core_v1.list_namespaced_persistent_volume_claim(
            validated_name(namespace)
        )
        return list_response(
            [summarize_pvc(p) for p in pvcs.items], "PersistentVolumeClaimList"
        )
    except ApiException as e:
        raise api_error(e)


def get_pvc_data(namespace: str, pvc_name: str) -> Dict[str, Any]:
    try:
        return summarize_pvc(
            core_v1.read_namespaced_persistent_volume_claim(
                validated_name(pvc_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "PersistentVolumeClaim not found")


def list_config_maps_data(namespace: str) -> Dict[str, Any]:
    try:
        cms = core_v1.list_namespaced_config_map(validated_name(namespace))
        return list_response(
            [summarize_config_map(c) for c in cms.items], "ConfigMapList"
        )
    except ApiException as e:
        raise api_error(e)


def get_config_map_data(namespace: str, cm_name: str) -> Dict[str, Any]:
    try:
        return summarize_config_map(
            core_v1.read_namespaced_config_map(
                validated_name(cm_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "ConfigMap not found")


def list_service_accounts_data(namespace: str) -> Dict[str, Any]:
    try:
        sas = core_v1.list_namespaced_service_account(validated_name(namespace))
        return list_response(
            [summarize_service_account(s) for s in sas.items], "ServiceAccountList"
        )
    except ApiException as e:
        raise api_error(e)


def get_service_account_data(namespace: str, sa_name: str) -> Dict[str, Any]:
    try:
        return summarize_service_account(
            core_v1.read_namespaced_service_account(
                validated_name(sa_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "ServiceAccount not found")


def list_resource_quotas_data(namespace: str) -> Dict[str, Any]:
    try:
        rqs = core_v1.list_namespaced_resource_quota(validated_name(namespace))
        return list_response(
            [summarize_resource_quota(r) for r in rqs.items], "ResourceQuotaList"
        )
    except ApiException as e:
        raise api_error(e)


def get_resource_quota_data(namespace: str, rq_name: str) -> Dict[str, Any]:
    try:
        return summarize_resource_quota(
            core_v1.read_namespaced_resource_quota(
                validated_name(rq_name), validated_name(namespace)
            )
        )
    except ApiException as e:
        raise api_error(e, "ResourceQuota not found")


def list_limit_ranges_data(namespace: str) -> Dict[str, Any]:
    try:
        lrs = core_v1.list_namespaced_limit_range(validated_name(namespace))
        return list_response(
            [summarize_limit_range(r) for r in lrs.items], "LimitRangeList"
        )
    except ApiException as e:
        raise api_error(e)
