"""Tests for core Kubernetes REST endpoints (pods, nodes, services, storage,
configmaps, service accounts, quotas, events)."""

import os
import sys
from unittest.mock import patch

import pytest
from kubernetes import client as k8s
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _meta(name, namespace=None, uid="uid-1", labels=None):
    return k8s.V1ObjectMeta(
        name=name, namespace=namespace, uid=uid, resource_version="1", labels=labels
    )


class TestPods:
    """Test suite for pod endpoints."""

    def test_list_pods_success(self, client):
        from main import core_v1

        pod = k8s.V1Pod(
            metadata=_meta("my-pod", "my-ns"),
            spec=k8s.V1PodSpec(
                containers=[k8s.V1Container(name="app", image="nginx:1.0")],
                restart_policy="Always",
            ),
            status=k8s.V1PodStatus(phase="Running"),
        )
        with patch.object(
            core_v1, "list_namespaced_pod", return_value=k8s.V1PodList(items=[pod])
        ):
            response = client.get("/api/v1/namespaces/my-ns/pods")

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "PodList"
        assert data["count"] == 1
        assert data["items"][0]["name"] == "my-pod"
        assert data["items"][0]["phase"] == "Running"
        assert data["items"][0]["containers"][0]["name"] == "app"

    def test_get_pod_success(self, client):
        from main import core_v1

        pod = k8s.V1Pod(
            metadata=_meta("my-pod", "my-ns"),
            spec=k8s.V1PodSpec(
                containers=[k8s.V1Container(name="app", image="nginx:1.0")],
                restart_policy="Always",
            ),
            status=k8s.V1PodStatus(phase="Running"),
        )
        with patch.object(core_v1, "read_namespaced_pod", return_value=pod):
            response = client.get("/api/v1/namespaces/my-ns/pods/my-pod")

        assert response.status_code == 200
        assert response.json()["name"] == "my-pod"

    def test_get_pod_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1, "read_namespaced_pod", side_effect=ApiException(status=404)
        ):
            response = client.get("/api/v1/namespaces/my-ns/pods/missing")

        assert response.status_code == 404

    def test_delete_pod_success(self, client):
        from main import core_v1

        with patch.object(
            core_v1,
            "delete_namespaced_pod",
            return_value=k8s.V1Status(status="Success"),
        ) as delete_call:
            response = client.request("DELETE", "/api/v1/namespaces/my-ns/pods/my-pod")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "delete_requested"
        assert data["name"] == "my-pod"
        delete_call.assert_called_once()

    def test_get_pod_logs_success(self, client):
        from main import core_v1

        with patch.object(
            core_v1, "read_namespaced_pod_log", return_value="log line 1\nlog line 2"
        ) as logs_call:
            response = client.get(
                "/api/v1/namespaces/my-ns/pods/my-pod/logs",
                params={"container": "app", "tail_lines": 50},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["logs"] == "log line 1\nlog line 2"
        assert data["container"] == "app"
        logs_call.assert_called_once()
        assert logs_call.call_args.kwargs["tail_lines"] == 50

    def test_get_pod_logs_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1,
            "read_namespaced_pod_log",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/pods/missing/logs")

        assert response.status_code == 404

    def test_list_pod_events(self, client):
        from main import core_v1

        event = k8s.CoreV1Event(
            metadata=_meta("evt-1", "my-ns"),
            involved_object=k8s.V1ObjectReference(name="my-pod", kind="Pod"),
            type="Normal",
            reason="Scheduled",
            message="Successfully assigned",
            count=1,
        )
        with patch.object(
            core_v1,
            "list_namespaced_event",
            return_value=k8s.CoreV1EventList(items=[event]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/pods/my-pod/events")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"][0]["reason"] == "Scheduled"


class TestContainers:
    """Test suite for the aggregated containers endpoint."""

    def test_list_containers_across_pods(self, client):
        from main import core_v1

        pod = k8s.V1Pod(
            metadata=_meta("my-pod", "my-ns"),
            spec=k8s.V1PodSpec(
                containers=[
                    k8s.V1Container(name="app", image="nginx:1.0"),
                    k8s.V1Container(name="sidecar", image="envoy:1.0"),
                ],
                restart_policy="Always",
            ),
            status=k8s.V1PodStatus(phase="Running"),
        )
        with patch.object(
            core_v1, "list_namespaced_pod", return_value=k8s.V1PodList(items=[pod])
        ):
            response = client.get("/api/v1/namespaces/my-ns/containers")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert {c["name"] for c in data["items"]} == {"app", "sidecar"}


class TestNodes:
    """Test suite for node endpoints."""

    def test_list_nodes_success(self, client):
        from main import core_v1

        node = k8s.V1Node(
            metadata=_meta("node-1", labels={"node-role.kubernetes.io/worker": ""}),
            spec=k8s.V1NodeSpec(),
            status=k8s.V1NodeStatus(
                node_info=k8s.V1NodeSystemInfo(
                    architecture="amd64",
                    os_image="RHEL 9",
                    kernel_version="5.14",
                    container_runtime_version="cri-o",
                    kubelet_version="v1.29",
                    boot_id="boot-1",
                    kube_proxy_version="v1.29",
                    machine_id="machine-1",
                    operating_system="linux",
                    system_uuid="uuid-1",
                ),
                conditions=[k8s.V1NodeCondition(type="Ready", status="True")],
            ),
        )
        with patch.object(
            core_v1, "list_node", return_value=k8s.V1NodeList(items=[node])
        ):
            response = client.get("/api/v1/nodes")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"][0]["ready"] is True
        assert data["items"][0]["roles"] == ["worker"]

    def test_get_node_success(self, client):
        from main import core_v1

        node = k8s.V1Node(
            metadata=_meta("node-1"),
            spec=k8s.V1NodeSpec(),
            status=k8s.V1NodeStatus(),
        )
        with patch.object(core_v1, "read_node", return_value=node):
            response = client.get("/api/v1/nodes/node-1")

        assert response.status_code == 200
        assert response.json()["name"] == "node-1"

    def test_get_node_not_found(self, client):
        from main import core_v1

        with patch.object(core_v1, "read_node", side_effect=ApiException(status=404)):
            response = client.get("/api/v1/nodes/missing")

        assert response.status_code == 404


class TestServices:
    """Test suite for service endpoints."""

    def test_list_services(self, client):
        from main import core_v1

        svc = k8s.V1Service(
            metadata=_meta("my-svc", "my-ns"),
            spec=k8s.V1ServiceSpec(
                type="ClusterIP", cluster_ip="10.0.0.1", selector={"app": "my-svc"}
            ),
        )
        with patch.object(
            core_v1,
            "list_namespaced_service",
            return_value=k8s.V1ServiceList(items=[svc]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/services")

        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["type"] == "ClusterIP"

    def test_get_service_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1, "read_namespaced_service", side_effect=ApiException(status=404)
        ):
            response = client.get("/api/v1/namespaces/my-ns/services/missing")

        assert response.status_code == 404


class TestStorage:
    """Test suite for PersistentVolumes, PVCs, and StorageClasses."""

    def test_list_persistent_volumes(self, client):
        from main import core_v1

        pv = k8s.V1PersistentVolume(
            metadata=_meta("pv-1"),
            spec=k8s.V1PersistentVolumeSpec(
                capacity={"storage": "10Gi"}, access_modes=["ReadWriteOnce"]
            ),
            status=k8s.V1PersistentVolumeStatus(phase="Bound"),
        )
        with patch.object(
            core_v1,
            "list_persistent_volume",
            return_value=k8s.V1PersistentVolumeList(items=[pv]),
        ):
            response = client.get("/api/v1/persistentvolumes")

        assert response.status_code == 200
        assert response.json()["items"][0]["status"] == "Bound"

    def test_get_persistent_volume_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1, "read_persistent_volume", side_effect=ApiException(status=404)
        ):
            response = client.get("/api/v1/persistentvolumes/missing")

        assert response.status_code == 404

    def test_list_storage_classes(self, client):
        from main import storage_v1

        sc = k8s.V1StorageClass(
            metadata=_meta("standard"), provisioner="kubernetes.io/aws-ebs"
        )
        with patch.object(
            storage_v1,
            "list_storage_class",
            return_value=k8s.V1StorageClassList(items=[sc]),
        ):
            response = client.get("/api/v1/storageclasses")

        assert response.status_code == 200
        assert response.json()["items"][0]["provisioner"] == "kubernetes.io/aws-ebs"

    def test_list_pvcs(self, client):
        from main import core_v1

        pvc = k8s.V1PersistentVolumeClaim(
            metadata=_meta("my-pvc", "my-ns"),
            spec=k8s.V1PersistentVolumeClaimSpec(),
            status=k8s.V1PersistentVolumeClaimStatus(phase="Bound"),
        )
        with patch.object(
            core_v1,
            "list_namespaced_persistent_volume_claim",
            return_value=k8s.V1PersistentVolumeClaimList(items=[pvc]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/persistentvolumeclaims")

        assert response.status_code == 200
        assert response.json()["items"][0]["status"] == "Bound"

    def test_get_pvc_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1,
            "read_namespaced_persistent_volume_claim",
            side_effect=ApiException(status=404),
        ):
            response = client.get(
                "/api/v1/namespaces/my-ns/persistentvolumeclaims/missing"
            )

        assert response.status_code == 404


class TestConfigMapsAndServiceAccounts:
    """Test suite for ConfigMaps and ServiceAccounts."""

    def test_list_config_maps(self, client):
        from main import core_v1

        cm = k8s.V1ConfigMap(metadata=_meta("my-cm", "my-ns"), data={"key": "value"})
        with patch.object(
            core_v1,
            "list_namespaced_config_map",
            return_value=k8s.V1ConfigMapList(items=[cm]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/configmaps")

        assert response.status_code == 200
        assert response.json()["items"][0]["data"] == {"key": "value"}

    def test_get_config_map_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1,
            "read_namespaced_config_map",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/configmaps/missing")

        assert response.status_code == 404

    def test_list_service_accounts(self, client):
        from main import core_v1

        sa = k8s.V1ServiceAccount(
            metadata=_meta("my-sa", "my-ns"), automount_service_account_token=True
        )
        with patch.object(
            core_v1,
            "list_namespaced_service_account",
            return_value=k8s.V1ServiceAccountList(items=[sa]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/serviceaccounts")

        assert response.status_code == 200
        assert response.json()["items"][0]["automount_service_account_token"] is True

    def test_get_service_account_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1,
            "read_namespaced_service_account",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/serviceaccounts/missing")

        assert response.status_code == 404


class TestQuotasAndLimits:
    """Test suite for ResourceQuotas and LimitRanges."""

    def test_list_resource_quotas(self, client):
        from main import core_v1

        rq = k8s.V1ResourceQuota(
            metadata=_meta("my-rq", "my-ns"),
            spec=k8s.V1ResourceQuotaSpec(hard={"pods": "10"}),
            status=k8s.V1ResourceQuotaStatus(used={"pods": "3"}),
        )
        with patch.object(
            core_v1,
            "list_namespaced_resource_quota",
            return_value=k8s.V1ResourceQuotaList(items=[rq]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/resourcequotas")

        assert response.status_code == 200
        assert response.json()["items"][0]["hard"] == {"pods": "10"}

    def test_get_resource_quota_not_found(self, client):
        from main import core_v1

        with patch.object(
            core_v1,
            "read_namespaced_resource_quota",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/resourcequotas/missing")

        assert response.status_code == 404

    def test_list_limit_ranges(self, client):
        from main import core_v1

        lr = k8s.V1LimitRange(
            metadata=_meta("my-lr", "my-ns"), spec=k8s.V1LimitRangeSpec(limits=[])
        )
        with patch.object(
            core_v1,
            "list_namespaced_limit_range",
            return_value=k8s.V1LimitRangeList(items=[lr]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/limitranges")

        assert response.status_code == 200
        assert response.json()["count"] == 1


class TestNamespaceEvents:
    """Test suite for the namespace-level events endpoint."""

    def test_list_events_filters_by_object(self, client):
        from main import core_v1

        with patch.object(
            core_v1,
            "list_namespaced_event",
            return_value=k8s.CoreV1EventList(items=[]),
        ) as list_call:
            response = client.get(
                "/api/v1/namespaces/my-ns/events",
                params={
                    "involved_object_name": "my-pod",
                    "involved_object_kind": "Pod",
                },
            )

        assert response.status_code == 200
        field_selector = list_call.call_args.kwargs["field_selector"]
        assert "involvedObject.name=my-pod" in field_selector
        assert "involvedObject.kind=Pod" in field_selector
