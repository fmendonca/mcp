"""Tests for Kubernetes apps (Deployments, StatefulSets, DaemonSets,
ReplicaSets, HPAs, Ingresses, NetworkPolicies), batch (Jobs, CronJobs) and
RBAC (Roles, RoleBindings, ClusterRoles, ClusterRoleBindings) REST endpoints.
"""

import os
import sys
from unittest.mock import patch

import pytest
from kubernetes import client as k8s
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _meta(name, namespace=None, uid="uid-1", generation=None):
    return k8s.V1ObjectMeta(
        name=name,
        namespace=namespace,
        uid=uid,
        resource_version="1",
        generation=generation,
    )


class TestDeployments:
    """Test suite for deployment endpoints."""

    def test_list_deployments(self, client):
        from main import apps_v1

        dep = k8s.V1Deployment(
            metadata=_meta("my-dep", "my-ns"),
            spec=k8s.V1DeploymentSpec(
                replicas=3,
                selector=k8s.V1LabelSelector(match_labels={"app": "my-dep"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="app", image="nginx:1.0")]
                    )
                ),
            ),
            status=k8s.V1DeploymentStatus(
                ready_replicas=3, available_replicas=3, updated_replicas=3
            ),
        )
        with patch.object(
            apps_v1,
            "list_namespaced_deployment",
            return_value=k8s.V1DeploymentList(items=[dep]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/deployments")

        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["replicas"] == 3
        assert data["items"][0]["ready_replicas"] == 3

    def test_get_deployment_not_found(self, client):
        from main import apps_v1

        with patch.object(
            apps_v1,
            "read_namespaced_deployment",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/deployments/missing")

        assert response.status_code == 404

    def test_rollout_restart_deployment(self, client):
        from main import apps_v1

        with patch.object(
            apps_v1, "patch_namespaced_deployment", return_value=None
        ) as patch_call:
            response = client.post(
                "/api/v1/namespaces/my-ns/deployments/my-dep/rollout/restart"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rollout_restart_requested"
        annotations = patch_call.call_args.args[2]["spec"]["template"]["metadata"][
            "annotations"
        ]
        assert "kubectl.kubernetes.io/restartedAt" in annotations

    def test_scale_deployment(self, client):
        from main import apps_v1

        with patch.object(
            apps_v1, "patch_namespaced_deployment", return_value=None
        ) as patch_call:
            response = client.post(
                "/api/v1/namespaces/my-ns/deployments/my-dep/scale",
                json={"replicas": 5},
            )

        assert response.status_code == 200
        assert response.json()["replicas"] == 5
        assert patch_call.call_args.args[2] == {"spec": {"replicas": 5}}

    def test_update_deployment_container_resources(self, client):
        from main import apps_v1

        container = k8s.V1Container(name="app", image="nginx:1.0")
        dep = k8s.V1Deployment(
            metadata=_meta("my-dep", "my-ns"),
            spec=k8s.V1DeploymentSpec(
                selector=k8s.V1LabelSelector(match_labels={"app": "my-dep"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(containers=[container])
                ),
            ),
            status=k8s.V1DeploymentStatus(),
        )
        with patch.object(
            apps_v1, "read_namespaced_deployment", return_value=dep
        ), patch.object(apps_v1, "patch_namespaced_deployment", return_value=dep):
            response = client.patch(
                "/api/v1/namespaces/my-ns/deployments/my-dep/containers/app/resources",
                json={"limits": {"cpu": "500m"}},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "resources_updated"

    def test_update_deployment_container_resources_missing_container(self, client):
        from main import apps_v1

        dep = k8s.V1Deployment(
            metadata=_meta("my-dep", "my-ns"),
            spec=k8s.V1DeploymentSpec(
                selector=k8s.V1LabelSelector(match_labels={"app": "my-dep"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="other", image="nginx:1.0")]
                    )
                ),
            ),
            status=k8s.V1DeploymentStatus(),
        )
        with patch.object(apps_v1, "read_namespaced_deployment", return_value=dep):
            response = client.patch(
                "/api/v1/namespaces/my-ns/deployments/my-dep/containers/app/resources",
                json={"limits": {"cpu": "500m"}},
            )

        assert response.status_code == 404


class TestStatefulSets:
    """Test suite for statefulset endpoints."""

    def test_list_statefulsets(self, client):
        from main import apps_v1

        ss = k8s.V1StatefulSet(
            metadata=_meta("my-ss", "my-ns"),
            spec=k8s.V1StatefulSetSpec(
                replicas=2,
                service_name="my-ss",
                selector=k8s.V1LabelSelector(match_labels={"app": "my-ss"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="app", image="nginx:1.0")]
                    )
                ),
            ),
            status=k8s.V1StatefulSetStatus(replicas=2, ready_replicas=2),
        )
        with patch.object(
            apps_v1,
            "list_namespaced_stateful_set",
            return_value=k8s.V1StatefulSetList(items=[ss]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/statefulsets")

        assert response.status_code == 200
        assert response.json()["items"][0]["service_name"] == "my-ss"

    def test_get_statefulset_not_found(self, client):
        from main import apps_v1

        with patch.object(
            apps_v1,
            "read_namespaced_stateful_set",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/statefulsets/missing")

        assert response.status_code == 404

    def test_rollout_restart_statefulset(self, client):
        from main import apps_v1

        with patch.object(apps_v1, "patch_namespaced_stateful_set", return_value=None):
            response = client.post(
                "/api/v1/namespaces/my-ns/statefulsets/my-ss/rollout/restart"
            )

        assert response.status_code == 200
        assert response.json()["status"] == "rollout_restart_requested"

    def test_scale_statefulset(self, client):
        from main import apps_v1

        with patch.object(apps_v1, "patch_namespaced_stateful_set", return_value=None):
            response = client.post(
                "/api/v1/namespaces/my-ns/statefulsets/my-ss/scale",
                json={"replicas": 4},
            )

        assert response.status_code == 200
        assert response.json()["replicas"] == 4


class TestDaemonSetsAndReplicaSets:
    """Test suite for daemonset and replicaset endpoints."""

    def test_list_daemonsets(self, client):
        from main import apps_v1

        ds = k8s.V1DaemonSet(
            metadata=_meta("my-ds", "my-ns"),
            spec=k8s.V1DaemonSetSpec(
                selector=k8s.V1LabelSelector(match_labels={"app": "my-ds"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="app", image="nginx:1.0")]
                    )
                ),
            ),
            status=k8s.V1DaemonSetStatus(
                current_number_scheduled=3,
                number_misscheduled=0,
                desired_number_scheduled=3,
                number_ready=3,
            ),
        )
        with patch.object(
            apps_v1,
            "list_namespaced_daemon_set",
            return_value=k8s.V1DaemonSetList(items=[ds]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/daemonsets")

        assert response.status_code == 200
        assert response.json()["items"][0]["desired_number_scheduled"] == 3

    def test_get_daemonset_not_found(self, client):
        from main import apps_v1

        with patch.object(
            apps_v1,
            "read_namespaced_daemon_set",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/daemonsets/missing")

        assert response.status_code == 404

    def test_list_replicasets(self, client):
        from main import apps_v1

        rs = k8s.V1ReplicaSet(
            metadata=_meta("my-rs", "my-ns"),
            spec=k8s.V1ReplicaSetSpec(
                selector=k8s.V1LabelSelector(match_labels={"app": "my-rs"}),
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="app", image="nginx:1.0")]
                    )
                ),
            ),
            status=k8s.V1ReplicaSetStatus(replicas=1, ready_replicas=1),
        )
        with patch.object(
            apps_v1,
            "list_namespaced_replica_set",
            return_value=k8s.V1ReplicaSetList(items=[rs]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/replicasets")

        assert response.status_code == 200
        assert response.json()["count"] == 1


class TestHpasIngressesNetworkPolicies:
    """Test suite for HPA, Ingress, and NetworkPolicy endpoints."""

    def test_list_hpas(self, client):
        from main import autoscaling_v2

        hpa = k8s.V2HorizontalPodAutoscaler(
            metadata=_meta("my-hpa", "my-ns"),
            spec=k8s.V2HorizontalPodAutoscalerSpec(
                scale_target_ref=k8s.V2CrossVersionObjectReference(
                    kind="Deployment", name="my-dep"
                ),
                min_replicas=1,
                max_replicas=5,
            ),
            status=k8s.V2HorizontalPodAutoscalerStatus(
                current_replicas=2, desired_replicas=3
            ),
        )
        with patch.object(
            autoscaling_v2,
            "list_namespaced_horizontal_pod_autoscaler",
            return_value=k8s.V2HorizontalPodAutoscalerList(items=[hpa]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/hpas")

        assert response.status_code == 200
        assert response.json()["items"][0]["max_replicas"] == 5

    def test_get_hpa_not_found(self, client):
        from main import autoscaling_v2

        with patch.object(
            autoscaling_v2,
            "read_namespaced_horizontal_pod_autoscaler",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/hpas/missing")

        assert response.status_code == 404

    def test_list_ingresses(self, client):
        from main import networking_v1

        ing = k8s.V1Ingress(
            metadata=_meta("my-ing", "my-ns"),
            spec=k8s.V1IngressSpec(ingress_class_name="nginx"),
        )
        with patch.object(
            networking_v1,
            "list_namespaced_ingress",
            return_value=k8s.V1IngressList(items=[ing]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/ingresses")

        assert response.status_code == 200
        assert response.json()["items"][0]["ingress_class_name"] == "nginx"

    def test_get_ingress_not_found(self, client):
        from main import networking_v1

        with patch.object(
            networking_v1,
            "read_namespaced_ingress",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/ingresses/missing")

        assert response.status_code == 404

    def test_list_network_policies(self, client):
        from main import networking_v1

        np = k8s.V1NetworkPolicy(
            metadata=_meta("my-np", "my-ns"),
            spec=k8s.V1NetworkPolicySpec(
                pod_selector=k8s.V1LabelSelector(), policy_types=["Ingress"]
            ),
        )
        with patch.object(
            networking_v1,
            "list_namespaced_network_policy",
            return_value=k8s.V1NetworkPolicyList(items=[np]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/networkpolicies")

        assert response.status_code == 200
        assert response.json()["items"][0]["policy_types"] == ["Ingress"]


class TestJobsAndCronJobs:
    """Test suite for Job and CronJob endpoints."""

    def test_list_jobs(self, client):
        from main import batch_v1

        job = k8s.V1Job(
            metadata=_meta("my-job", "my-ns"),
            spec=k8s.V1JobSpec(
                template=k8s.V1PodTemplateSpec(
                    spec=k8s.V1PodSpec(
                        containers=[k8s.V1Container(name="app", image="busybox")],
                        restart_policy="Never",
                    )
                )
            ),
            status=k8s.V1JobStatus(active=1, succeeded=0, failed=0),
        )
        with patch.object(
            batch_v1, "list_namespaced_job", return_value=k8s.V1JobList(items=[job])
        ):
            response = client.get("/api/v1/namespaces/my-ns/jobs")

        assert response.status_code == 200
        assert response.json()["items"][0]["active"] == 1

    def test_get_job_not_found(self, client):
        from main import batch_v1

        with patch.object(
            batch_v1, "read_namespaced_job", side_effect=ApiException(status=404)
        ):
            response = client.get("/api/v1/namespaces/my-ns/jobs/missing")

        assert response.status_code == 404

    def test_list_cronjobs(self, client):
        from main import batch_v1

        cj = k8s.V1CronJob(
            metadata=_meta("my-cj", "my-ns"),
            spec=k8s.V1CronJobSpec(
                schedule="*/5 * * * *",
                job_template=k8s.V1JobTemplateSpec(
                    spec=k8s.V1JobSpec(
                        template=k8s.V1PodTemplateSpec(
                            spec=k8s.V1PodSpec(
                                containers=[
                                    k8s.V1Container(name="app", image="busybox")
                                ],
                                restart_policy="Never",
                            )
                        )
                    )
                ),
            ),
            status=k8s.V1CronJobStatus(),
        )
        with patch.object(
            batch_v1,
            "list_namespaced_cron_job",
            return_value=k8s.V1CronJobList(items=[cj]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/cronjobs")

        assert response.status_code == 200
        assert response.json()["items"][0]["schedule"] == "*/5 * * * *"

    def test_get_cronjob_not_found(self, client):
        from main import batch_v1

        with patch.object(
            batch_v1,
            "read_namespaced_cron_job",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/cronjobs/missing")

        assert response.status_code == 404


class TestRbac:
    """Test suite for namespaced and cluster-scoped RBAC endpoints."""

    def test_list_roles(self, client):
        from main import rbac_v1

        role = k8s.V1Role(
            metadata=_meta("my-role", "my-ns"),
            rules=[k8s.V1PolicyRule(verbs=["get", "list"], resources=["pods"])],
        )
        with patch.object(
            rbac_v1, "list_namespaced_role", return_value=k8s.V1RoleList(items=[role])
        ):
            response = client.get("/api/v1/namespaces/my-ns/rbac/roles")

        assert response.status_code == 200
        assert response.json()["items"][0]["rules"][0]["verbs"] == ["get", "list"]

    def test_get_role_not_found(self, client):
        from main import rbac_v1

        with patch.object(
            rbac_v1, "read_namespaced_role", side_effect=ApiException(status=404)
        ):
            response = client.get("/api/v1/namespaces/my-ns/rbac/roles/missing")

        assert response.status_code == 404

    def test_list_role_bindings(self, client):
        from main import rbac_v1

        rb = k8s.V1RoleBinding(
            metadata=_meta("my-rb", "my-ns"),
            role_ref=k8s.V1RoleRef(
                api_group="rbac.authorization.k8s.io", kind="Role", name="my-role"
            ),
            subjects=[
                k8s.RbacV1Subject(kind="ServiceAccount", name="sa", namespace="my-ns")
            ],
        )
        with patch.object(
            rbac_v1,
            "list_namespaced_role_binding",
            return_value=k8s.V1RoleBindingList(items=[rb]),
        ):
            response = client.get("/api/v1/namespaces/my-ns/rbac/rolebindings")

        assert response.status_code == 200
        assert response.json()["items"][0]["role_ref"]["name"] == "my-role"

    def test_get_role_binding_not_found(self, client):
        from main import rbac_v1

        with patch.object(
            rbac_v1,
            "read_namespaced_role_binding",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/namespaces/my-ns/rbac/rolebindings/missing")

        assert response.status_code == 404

    def test_list_cluster_roles(self, client):
        from main import rbac_v1

        cr = k8s.V1ClusterRole(
            metadata=_meta("my-cr"),
            rules=[k8s.V1PolicyRule(verbs=["*"], resources=["*"])],
        )
        with patch.object(
            rbac_v1,
            "list_cluster_role",
            return_value=k8s.V1ClusterRoleList(items=[cr]),
        ):
            response = client.get("/api/v1/rbac/clusterroles")

        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_get_cluster_role_not_found(self, client):
        from main import rbac_v1

        with patch.object(
            rbac_v1, "read_cluster_role", side_effect=ApiException(status=404)
        ):
            response = client.get("/api/v1/rbac/clusterroles/missing")

        assert response.status_code == 404

    def test_list_cluster_role_bindings(self, client):
        from main import rbac_v1

        crb = k8s.V1ClusterRoleBinding(
            metadata=_meta("my-crb"),
            role_ref=k8s.V1RoleRef(
                api_group="rbac.authorization.k8s.io",
                kind="ClusterRole",
                name="my-cr",
            ),
            subjects=[k8s.RbacV1Subject(kind="ServiceAccount", name="sa")],
        )
        with patch.object(
            rbac_v1,
            "list_cluster_role_binding",
            return_value=k8s.V1ClusterRoleBindingList(items=[crb]),
        ):
            response = client.get("/api/v1/rbac/clusterrolebindings")

        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_get_cluster_role_binding_not_found(self, client):
        from main import rbac_v1

        with patch.object(
            rbac_v1,
            "read_cluster_role_binding",
            side_effect=ApiException(status=404),
        ):
            response = client.get("/api/v1/rbac/clusterrolebindings/missing")

        assert response.status_code == 404
