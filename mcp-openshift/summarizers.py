"""Summarizer functions that convert Kubernetes/OpenShift/KubeVirt API
objects (SDK model instances or raw CRD dicts) into JSON-serializable dicts.
"""

from typing import Any, Dict, List, Optional


def list_response(items: List[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    return {"kind": kind, "count": len(items), "items": items}


# --- Summarizers: Kubernetes core ---
def object_metadata(obj: Any) -> Dict[str, Any]:
    return {
        "name": obj.metadata.name,
        "namespace": obj.metadata.namespace,
        "uid": obj.metadata.uid,
        "resource_version": obj.metadata.resource_version,
        "labels": obj.metadata.labels or {},
        "annotations": obj.metadata.annotations or {},
        "created_at": (
            obj.metadata.creation_timestamp.isoformat()
            if obj.metadata.creation_timestamp
            else None
        ),
    }


def container_resources(container: Any) -> Dict[str, Any]:
    resources = container.resources
    if not resources:
        return {"limits": {}, "requests": {}}
    return {"limits": resources.limits or {}, "requests": resources.requests or {}}


def summarize_container(container: Any, status: Optional[Any] = None) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "name": container.name,
        "image": container.image,
        "image_pull_policy": container.image_pull_policy,
        "resources": container_resources(container),
        "ports": [port.to_dict() for port in (container.ports or [])],
    }
    if status:
        data.update(
            {
                "ready": status.ready,
                "started": status.started,
                "restart_count": status.restart_count,
                "image_id": status.image_id,
                "container_id": status.container_id,
                "state": status.state.to_dict() if status.state else None,
                "last_state": (
                    status.last_state.to_dict() if status.last_state else None
                ),
            }
        )
    return data


def summarize_namespace(namespace: Any) -> Dict[str, Any]:
    return {
        **object_metadata(namespace),
        "status": namespace.status.phase,
        "conditions": [c.to_dict() for c in (namespace.status.conditions or [])],
    }


def summarize_node(node: Any) -> Dict[str, Any]:
    labels = node.metadata.labels or {}
    roles = [
        k.split("/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/")
    ] or ["worker"]
    ni = node.status.node_info
    conditions = {c.type: c.status for c in (node.status.conditions or [])}
    return {
        **object_metadata(node),
        "roles": roles,
        "ready": conditions.get("Ready") == "True",
        "unschedulable": node.spec.unschedulable or False,
        "addresses": [a.to_dict() for a in (node.status.addresses or [])],
        "capacity": node.status.capacity or {},
        "allocatable": node.status.allocatable or {},
        "architecture": ni.architecture if ni else None,
        "os_image": ni.os_image if ni else None,
        "kernel_version": ni.kernel_version if ni else None,
        "container_runtime": ni.container_runtime_version if ni else None,
        "kubelet_version": ni.kubelet_version if ni else None,
        "conditions": [c.to_dict() for c in (node.status.conditions or [])],
        "taints": [t.to_dict() for t in (node.spec.taints or [])],
    }


def summarize_pod(pod: Any) -> Dict[str, Any]:
    statuses = {s.name: s for s in (pod.status.container_statuses or [])}
    return {
        **object_metadata(pod),
        "phase": pod.status.phase,
        "pod_ip": pod.status.pod_ip,
        "host_ip": pod.status.host_ip,
        "node_name": pod.spec.node_name,
        "qos_class": pod.status.qos_class,
        "restart_policy": pod.spec.restart_policy,
        "service_account": pod.spec.service_account_name,
        "containers": [
            summarize_container(c, statuses.get(c.name))
            for c in (pod.spec.containers or [])
        ],
        "init_containers": [
            summarize_container(c) for c in (pod.spec.init_containers or [])
        ],
        "conditions": [c.to_dict() for c in (pod.status.conditions or [])],
    }


def summarize_persistent_volume(pv: Any) -> Dict[str, Any]:
    return {
        **object_metadata(pv),
        "capacity": pv.spec.capacity or {},
        "access_modes": pv.spec.access_modes or [],
        "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
        "storage_class": pv.spec.storage_class_name,
        "volume_mode": pv.spec.volume_mode,
        "status": pv.status.phase,
        "claim_ref": pv.spec.claim_ref.to_dict() if pv.spec.claim_ref else None,
    }


def summarize_pvc(pvc: Any) -> Dict[str, Any]:
    requested = None
    if pvc.spec.resources and pvc.spec.resources.requests:
        requested = pvc.spec.resources.requests.get("storage")
    return {
        **object_metadata(pvc),
        "status": pvc.status.phase,
        "capacity": pvc.status.capacity or {},
        "access_modes": pvc.status.access_modes or [],
        "storage_class": pvc.spec.storage_class_name,
        "volume_mode": pvc.spec.volume_mode,
        "volume_name": pvc.spec.volume_name,
        "requested_storage": requested,
    }


def summarize_storage_class(sc: Any) -> Dict[str, Any]:
    return {
        **object_metadata(sc),
        "provisioner": sc.provisioner,
        "reclaim_policy": sc.reclaim_policy,
        "volume_binding_mode": sc.volume_binding_mode,
        "allow_volume_expansion": sc.allow_volume_expansion,
        "parameters": sc.parameters or {},
    }


def summarize_config_map(cm: Any) -> Dict[str, Any]:
    return {
        **object_metadata(cm),
        "data": cm.data or {},
        "binary_data_keys": list(cm.binary_data.keys()) if cm.binary_data else [],
    }


def summarize_service_account(sa: Any) -> Dict[str, Any]:
    return {
        **object_metadata(sa),
        "secrets": [s.to_dict() for s in (sa.secrets or [])],
        "image_pull_secrets": [s.to_dict() for s in (sa.image_pull_secrets or [])],
        "automount_service_account_token": sa.automount_service_account_token,
    }


def summarize_resource_quota(rq: Any) -> Dict[str, Any]:
    return {
        **object_metadata(rq),
        "hard": rq.spec.hard or {},
        "used": rq.status.used or {},
        "scopes": rq.spec.scopes or [],
    }


def summarize_limit_range(lr: Any) -> Dict[str, Any]:
    return {
        **object_metadata(lr),
        "limits": [lim.to_dict() for lim in (lr.spec.limits or [])],
    }


def summarize_deployment(deployment: Any) -> Dict[str, Any]:
    desired = deployment.spec.replicas or 0
    updated = deployment.status.updated_replicas or 0
    available = deployment.status.available_replicas or 0
    observed = deployment.status.observed_generation or 0
    generation = deployment.metadata.generation or 0
    return {
        **object_metadata(deployment),
        "replicas": desired,
        "ready_replicas": deployment.status.ready_replicas or 0,
        "available_replicas": available,
        "updated_replicas": updated,
        "rollout_complete": observed >= generation
        and updated == desired
        and available == desired,
        "observed_generation": observed,
        "generation": generation,
        "strategy": (
            deployment.spec.strategy.to_dict() if deployment.spec.strategy else None
        ),
        "containers": [
            summarize_container(c)
            for c in (deployment.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (deployment.status.conditions or [])],
    }


def summarize_statefulset(ss: Any) -> Dict[str, Any]:
    return {
        **object_metadata(ss),
        "replicas": ss.spec.replicas or 0,
        "ready_replicas": ss.status.ready_replicas or 0,
        "current_replicas": ss.status.current_replicas or 0,
        "updated_replicas": ss.status.updated_replicas or 0,
        "service_name": ss.spec.service_name,
        "update_strategy": (
            ss.spec.update_strategy.to_dict() if ss.spec.update_strategy else None
        ),
        "containers": [
            summarize_container(c) for c in (ss.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (ss.status.conditions or [])],
    }


def summarize_daemonset(ds: Any) -> Dict[str, Any]:
    return {
        **object_metadata(ds),
        "desired_number_scheduled": ds.status.desired_number_scheduled or 0,
        "number_ready": ds.status.number_ready or 0,
        "number_available": ds.status.number_available or 0,
        "number_unavailable": ds.status.number_unavailable or 0,
        "updated_number_scheduled": ds.status.updated_number_scheduled or 0,
        "update_strategy": (
            ds.spec.update_strategy.to_dict() if ds.spec.update_strategy else None
        ),
        "containers": [
            summarize_container(c) for c in (ds.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (ds.status.conditions or [])],
    }


def summarize_replicaset(rs: Any) -> Dict[str, Any]:
    return {
        **object_metadata(rs),
        "replicas": rs.spec.replicas or 0,
        "ready_replicas": rs.status.ready_replicas or 0,
        "available_replicas": rs.status.available_replicas or 0,
        "owner_references": [r.to_dict() for r in (rs.metadata.owner_references or [])],
        "containers": [
            summarize_container(c) for c in (rs.spec.template.spec.containers or [])
        ],
        "conditions": [c.to_dict() for c in (rs.status.conditions or [])],
    }


def summarize_hpa(hpa: Any) -> Dict[str, Any]:
    return {
        **object_metadata(hpa),
        "min_replicas": hpa.spec.min_replicas,
        "max_replicas": hpa.spec.max_replicas,
        "current_replicas": hpa.status.current_replicas or 0,
        "desired_replicas": hpa.status.desired_replicas or 0,
        "scale_target_ref": (
            hpa.spec.scale_target_ref.to_dict() if hpa.spec.scale_target_ref else None
        ),
        "metrics": [m.to_dict() for m in (hpa.spec.metrics or [])],
        "current_metrics": [m.to_dict() for m in (hpa.status.current_metrics or [])],
        "conditions": [c.to_dict() for c in (hpa.status.conditions or [])],
    }


def summarize_ingress(ingress: Any) -> Dict[str, Any]:
    lb = None
    if ingress.status and ingress.status.load_balancer:
        lb = ingress.status.load_balancer.to_dict()
    return {
        **object_metadata(ingress),
        "ingress_class_name": ingress.spec.ingress_class_name,
        "rules": [r.to_dict() for r in (ingress.spec.rules or [])],
        "tls": [t.to_dict() for t in (ingress.spec.tls or [])],
        "load_balancer": lb,
    }


def summarize_network_policy(np: Any) -> Dict[str, Any]:
    return {
        **object_metadata(np),
        "pod_selector": (
            np.spec.pod_selector.to_dict() if np.spec.pod_selector else None
        ),
        "ingress": [r.to_dict() for r in (np.spec.ingress or [])],
        "egress": [r.to_dict() for r in (np.spec.egress or [])],
        "policy_types": np.spec.policy_types or [],
    }


def summarize_job(job: Any) -> Dict[str, Any]:
    return {
        **object_metadata(job),
        "parallelism": job.spec.parallelism,
        "completions": job.spec.completions,
        "active": job.status.active or 0,
        "succeeded": job.status.succeeded or 0,
        "failed": job.status.failed or 0,
        "start_time": (
            job.status.start_time.isoformat() if job.status.start_time else None
        ),
        "completion_time": (
            job.status.completion_time.isoformat()
            if job.status.completion_time
            else None
        ),
        "conditions": [c.to_dict() for c in (job.status.conditions or [])],
    }


def summarize_cronjob(cronjob: Any) -> Dict[str, Any]:
    return {
        **object_metadata(cronjob),
        "schedule": cronjob.spec.schedule,
        "suspend": cronjob.spec.suspend,
        "active_jobs": [
            {"name": ref.name, "namespace": ref.namespace}
            for ref in (cronjob.status.active or [])
        ],
        "last_schedule_time": (
            cronjob.status.last_schedule_time.isoformat()
            if cronjob.status.last_schedule_time
            else None
        ),
        "last_successful_time": (
            cronjob.status.last_successful_time.isoformat()
            if cronjob.status.last_successful_time
            else None
        ),
    }


def summarize_service(service: Any) -> Dict[str, Any]:
    return {
        **object_metadata(service),
        "type": service.spec.type,
        "cluster_ip": service.spec.cluster_ip,
        "external_ips": service.spec.external_i_ps or [],
        "ports": [p.to_dict() for p in (service.spec.ports or [])],
        "selector": service.spec.selector or {},
    }


def summarize_event(event: Any) -> Dict[str, Any]:
    event_time = event.event_time or event.last_timestamp or event.first_timestamp
    return {
        **object_metadata(event),
        "type": event.type,
        "reason": event.reason,
        "message": event.message,
        "count": event.count,
        "involved_object": (
            event.involved_object.to_dict() if event.involved_object else None
        ),
        "event_time": event_time.isoformat() if event_time else None,
    }


def summarize_role(role: Any) -> Dict[str, Any]:
    return {
        **object_metadata(role),
        "rules": [r.to_dict() for r in (role.rules or [])],
    }


def summarize_binding(binding: Any) -> Dict[str, Any]:
    return {
        **object_metadata(binding),
        "role_ref": binding.role_ref.to_dict() if binding.role_ref else None,
        "subjects": [s.to_dict() for s in (binding.subjects or [])],
    }


# --- Summarizers: OpenShift custom resources (dicts from CustomObjectsApi) ---
def _meta(obj: Dict[str, Any]) -> Dict[str, Any]:
    m = obj.get("metadata", {})
    return {
        "name": m.get("name"),
        "namespace": m.get("namespace"),
        "uid": m.get("uid"),
        "labels": m.get("labels", {}),
        "annotations": m.get("annotations", {}),
        "created_at": m.get("creationTimestamp"),
    }


def summarize_route(route: Dict[str, Any]) -> Dict[str, Any]:
    spec = route.get("spec", {})
    status = route.get("status", {})
    return {
        **_meta(route),
        "host": spec.get("host"),
        "path": spec.get("path"),
        "to": spec.get("to"),
        "port": spec.get("port"),
        "tls": spec.get("tls"),
        "ingress": status.get("ingress", []),
    }


def summarize_project(proj: Dict[str, Any]) -> Dict[str, Any]:
    annotations = proj.get("metadata", {}).get("annotations", {})
    return {
        **_meta(proj),
        "status": proj.get("status", {}).get("phase"),
        "display_name": annotations.get("openshift.io/display-name", ""),
        "description": annotations.get("openshift.io/description", ""),
    }


def summarize_deployment_config(dc: Dict[str, Any]) -> Dict[str, Any]:
    spec = dc.get("spec", {})
    status = dc.get("status", {})
    containers = spec.get("template", {}).get("spec", {}).get("containers", [])
    return {
        **_meta(dc),
        "replicas": spec.get("replicas", 0),
        "ready_replicas": status.get("readyReplicas", 0),
        "available_replicas": status.get("availableReplicas", 0),
        "updated_replicas": status.get("updatedReplicas", 0),
        "latest_version": status.get("latestVersion"),
        "observed_generation": status.get("observedGeneration"),
        "strategy": spec.get("strategy", {}).get("type"),
        "containers": [
            {
                "name": c.get("name"),
                "image": c.get("image"),
                "resources": c.get("resources", {}),
            }
            for c in containers
        ],
        "triggers": [t.get("type") for t in spec.get("triggers", [])],
        "conditions": status.get("conditions", []),
    }


def summarize_build_config(bc: Dict[str, Any]) -> Dict[str, Any]:
    spec = bc.get("spec", {})
    return {
        **_meta(bc),
        "source_type": spec.get("source", {}).get("type"),
        "source_git": spec.get("source", {}).get("git", {}).get("uri"),
        "source_ref": spec.get("source", {}).get("git", {}).get("ref"),
        "output_to": spec.get("output", {}).get("to"),
        "strategy": spec.get("strategy", {}).get("type"),
        "last_version": bc.get("status", {}).get("lastVersion"),
        "triggers": [t.get("type") for t in spec.get("triggers", [])],
    }


def summarize_build(build: Dict[str, Any]) -> Dict[str, Any]:
    spec = build.get("spec", {})
    status = build.get("status", {})
    return {
        **_meta(build),
        "phase": status.get("phase"),
        "reason": status.get("reason"),
        "message": status.get("message"),
        "start_timestamp": status.get("startTimestamp"),
        "completion_timestamp": status.get("completionTimestamp"),
        "duration": status.get("duration"),
        "output_docker_image": status.get("outputDockerImageReference"),
        "strategy": spec.get("strategy", {}).get("type"),
    }


def summarize_image_stream(is_obj: Dict[str, Any]) -> Dict[str, Any]:
    status = is_obj.get("status", {})
    spec = is_obj.get("spec", {})
    return {
        **_meta(is_obj),
        "docker_image_repository": status.get("dockerImageRepository"),
        "public_docker_image_repository": status.get("publicDockerImageRepository"),
        "lookup_policy_local": spec.get("lookupPolicy", {}).get("local", False),
        "tags": [
            {
                "tag": t.get("tag"),
                "items": [
                    {
                        "created": item.get("created"),
                        "docker_image_reference": item.get("dockerImageReference"),
                        "image": item.get("image"),
                    }
                    for item in t.get("items", [])[:3]
                ],
            }
            for t in status.get("tags", [])
        ],
    }


def summarize_scc(scc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_meta(scc),
        "allow_privileged": scc.get("allowPrivilegedContainer", False),
        "allow_privilege_escalation": scc.get("allowPrivilegeEscalation"),
        "run_as_user": scc.get("runAsUser", {}),
        "se_linux_context": scc.get("seLinuxContext", {}),
        "fs_group": scc.get("fsGroup", {}),
        "supplemental_groups": scc.get("supplementalGroups", {}),
        "volumes": scc.get("volumes", []),
        "users": scc.get("users", []),
        "groups": scc.get("groups", []),
        "priority": scc.get("priority"),
    }


def summarize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_meta(user),
        "full_name": user.get("fullName", ""),
        "identities": user.get("identities", []),
        "groups": user.get("groups", []),
    }


def summarize_group(group: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_meta(group),
        "users": group.get("users", []),
    }


def summarize_cluster_version(cv: Dict[str, Any]) -> Dict[str, Any]:
    spec = cv.get("spec", {})
    status = cv.get("status", {})
    history = status.get("history", [])
    current = next(
        (h for h in history if h.get("state") == "Completed"),
        history[0] if history else {},
    )
    desired_update = spec.get("desiredUpdate")
    return {
        **_meta(cv),
        "cluster_id": spec.get("clusterID"),
        "channel": spec.get("channel"),
        "version": current.get("version"),
        "state": current.get("state"),
        "verified": current.get("verified"),
        "started_time": current.get("startedTime"),
        "completion_time": current.get("completionTime"),
        "desired_update": desired_update,
        "available_updates": [
            u.get("version") for u in status.get("availableUpdates", [])
        ],
        "conditions": status.get("conditions", []),
    }


def summarize_cluster_operator(co: Dict[str, Any]) -> Dict[str, Any]:
    status = co.get("status", {})
    conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
    operator_version = next(
        (
            v.get("version")
            for v in status.get("versions", [])
            if v.get("name") == "operator"
        ),
        None,
    )
    return {
        **_meta(co),
        "available": conditions.get("Available") == "True",
        "progressing": conditions.get("Progressing") == "True",
        "degraded": conditions.get("Degraded") == "True",
        "version": operator_version,
        "related_objects": status.get("relatedObjects", []),
        "conditions": status.get("conditions", []),
    }


def summarize_machine_config_pool(mcp_obj: Dict[str, Any]) -> Dict[str, Any]:
    spec = mcp_obj.get("spec", {})
    status = mcp_obj.get("status", {})
    conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
    return {
        **_meta(mcp_obj),
        "paused": spec.get("paused", False),
        "machine_count": status.get("machineCount", 0),
        "ready_machine_count": status.get("readyMachineCount", 0),
        "updated_machine_count": status.get("updatedMachineCount", 0),
        "unavailable_machine_count": status.get("unavailableMachineCount", 0),
        "degraded_machine_count": status.get("degradedMachineCount", 0),
        "updated": conditions.get("Updated") == "True",
        "updating": conditions.get("Updating") == "True",
        "degraded": conditions.get("Degraded") == "True",
        "configuration": status.get("configuration", {}).get("name"),
        "conditions": status.get("conditions", []),
    }


def summarize_machine(machine: Dict[str, Any]) -> Dict[str, Any]:
    spec = machine.get("spec", {})
    status = machine.get("status", {})
    conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
    return {
        **_meta(machine),
        "phase": status.get("phase"),
        "node_ref": (
            status.get("nodeRef", {}).get("name") if status.get("nodeRef") else None
        ),
        "provider_id": spec.get("providerID"),
        "ready": conditions.get("Ready") == "True",
        "conditions": status.get("conditions", []),
    }


def summarize_machine_set(ms: Dict[str, Any]) -> Dict[str, Any]:
    spec = ms.get("spec", {})
    status = ms.get("status", {})
    return {
        **_meta(ms),
        "replicas": spec.get("replicas", 0),
        "ready_replicas": status.get("readyReplicas", 0),
        "available_replicas": status.get("availableReplicas", 0),
        "fully_labeled_replicas": status.get("fullyLabeledReplicas", 0),
        "error_reason": status.get("errorReason"),
        "error_message": status.get("errorMessage"),
    }


def summarize_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    spec = sub.get("spec", {})
    status = sub.get("status", {})
    return {
        **_meta(sub),
        "package": spec.get("name"),
        "channel": spec.get("channel"),
        "source": spec.get("source"),
        "source_namespace": spec.get("sourceNamespace"),
        "install_plan_approval": spec.get("installPlanApproval"),
        "current_csv": status.get("currentCSV"),
        "installed_csv": status.get("installedCSV"),
        "state": status.get("state"),
        "conditions": status.get("conditions", []),
    }


def summarize_operator_group(og: Dict[str, Any]) -> Dict[str, Any]:
    spec = og.get("spec", {})
    status = og.get("status", {})
    return {
        **_meta(og),
        "target_namespaces": spec.get("targetNamespaces", []),
        "service_account_name": spec.get("serviceAccountName"),
        "namespaces": status.get("namespaces", []),
        "last_updated": status.get("lastUpdated"),
    }


def summarize_csv(csv_obj: Dict[str, Any]) -> Dict[str, Any]:
    spec = csv_obj.get("spec", {})
    status = csv_obj.get("status", {})
    return {
        **_meta(csv_obj),
        "display_name": spec.get("displayName"),
        "version": spec.get("version"),
        "maturity": spec.get("maturity"),
        "phase": status.get("phase"),
        "reason": status.get("reason"),
        "conditions": [
            {
                "type": c.get("type"),
                "status": c.get("status"),
                "message": (c.get("message") or "")[:200],
            }
            for c in status.get("conditions", [])
        ],
    }


def summarize_catalog_source(cs: Dict[str, Any]) -> Dict[str, Any]:
    spec = cs.get("spec", {})
    status = cs.get("status", {})
    poll_interval = None
    if spec.get("updateStrategy", {}).get("registryPoll"):
        poll_interval = spec["updateStrategy"]["registryPoll"].get("interval")
    return {
        **_meta(cs),
        "source_type": spec.get("sourceType"),
        "image": spec.get("image"),
        "display_name": spec.get("displayName"),
        "publisher": spec.get("publisher"),
        "registry_poll_interval": poll_interval,
        "last_observed_state": status.get("connectionState", {}).get(
            "lastObservedState"
        ),
    }


def summarize_virtualmachine(vm: Dict[str, Any]) -> Dict[str, Any]:
    spec = vm.get("spec", {})
    status = vm.get("status", {})
    return {
        **_meta(vm),
        "running": spec.get("running"),
        "phase": status.get("printableStatus"),
        "ready": status.get("ready", False),
        "created": status.get("created", False),
        "volume_snapshot_statuses": status.get("volumeSnapshotStatuses", []),
        "state_change_requests": status.get("stateChangeRequests", []),
    }


def summarize_vmi(vmi: Dict[str, Any]) -> Dict[str, Any]:
    status = vmi.get("status", {})
    interfaces = status.get("interfaces", [])
    return {
        **_meta(vmi),
        "phase": status.get("phase"),
        "node_name": status.get("nodeName"),
        "ip_address": interfaces[0].get("ipAddress") if interfaces else None,
        "ip_addresses": [i.get("ipAddress") for i in interfaces if i.get("ipAddress")],
        "guest_os": status.get("guestOSInfo", {}).get("name"),
        "ready": any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in status.get("conditions", [])
        ),
        "live_migratable": any(
            c.get("type") == "LiveMigratable" and c.get("status") == "True"
            for c in status.get("conditions", [])
        ),
        "conditions": status.get("conditions", []),
    }
