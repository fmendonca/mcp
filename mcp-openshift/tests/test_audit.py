"""Tests for the structured audit log on mutating operations."""

import json
import logging
import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from kubernetes import client as k8s
from kubernetes.client.rest import ApiException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_apps  # noqa: E402
import data_core  # noqa: E402
from audit import audited  # noqa: E402
from config import apps_v1, core_v1  # noqa: E402


def _audit_records(caplog):
    return [
        json.loads(r.message) for r in caplog.records if r.name == "mcp_openshift.audit"
    ]


class TestAuditedDecorator:
    """Unit behavior of @audited itself."""

    def test_success_record_includes_scalar_args(self, caplog):
        @audited("do_thing")
        def do_thing(namespace, count=3, options=None):
            return {"ok": True}

        with caplog.at_level(logging.INFO, logger="mcp_openshift.audit"):
            do_thing("my-ns", options=object())

        records = _audit_records(caplog)
        assert len(records) == 1
        record = records[0]
        assert record["action"] == "do_thing"
        assert record["outcome"] == "success"
        assert record["namespace"] == "my-ns"
        assert record["count"] == 3
        # non-scalar args (request bodies etc.) never land in the trail
        assert "options" not in record
        assert "timestamp" in record

    def test_http_exception_records_error_with_status(self, caplog):
        @audited("do_thing")
        def do_thing(namespace):
            raise HTTPException(status_code=409, detail="conflict")

        with caplog.at_level(logging.INFO, logger="mcp_openshift.audit"):
            with pytest.raises(HTTPException):
                do_thing("my-ns")

        record = _audit_records(caplog)[0]
        assert record["outcome"] == "error"
        assert record["status_code"] == 409

    def test_unexpected_exception_still_audited(self, caplog):
        @audited("do_thing")
        def do_thing(namespace):
            raise RuntimeError("boom")

        with caplog.at_level(logging.INFO, logger="mcp_openshift.audit"):
            with pytest.raises(RuntimeError):
                do_thing("my-ns")

        record = _audit_records(caplog)[0]
        assert record["outcome"] == "error"
        assert "status_code" not in record


class TestMutatingFunctionsAreAudited:
    """Representative end-to-end checks that real mutations emit records."""

    def test_delete_pod_emits_audit(self, caplog):
        with (
            caplog.at_level(logging.INFO, logger="mcp_openshift.audit"),
            patch.object(
                core_v1,
                "delete_namespaced_pod",
                return_value=k8s.V1Status(status="Success"),
            ),
        ):
            data_core.delete_pod_data("my-ns", "my-pod")

        record = _audit_records(caplog)[0]
        assert record["action"] == "delete_pod"
        assert record["outcome"] == "success"
        assert record["namespace"] == "my-ns"
        assert record["pod_name"] == "my-pod"

    def test_scale_deployment_failure_emits_audit(self, caplog):
        with (
            caplog.at_level(logging.INFO, logger="mcp_openshift.audit"),
            patch.object(
                apps_v1,
                "patch_namespaced_deployment",
                side_effect=ApiException(status=403),
            ),
        ):
            with pytest.raises(HTTPException):
                data_apps.scale_deployment_data("my-ns", "my-dep", 5)

        record = _audit_records(caplog)[0]
        assert record["action"] == "scale_deployment"
        assert record["outcome"] == "error"
        assert record["status_code"] == 403
        assert record["replicas"] == 5

    def test_every_planned_mutation_is_decorated(self):
        """Guard: the mutating data functions carry the audit wrapper."""
        import data_kubevirt
        import data_olm
        import data_openshift

        audited_funcs = [
            data_core.create_namespace_data,
            data_core.delete_pod_data,
            data_apps.rollout_restart_deployment_data,
            data_apps.scale_deployment_data,
            data_apps.update_deployment_container_resources_data,
            data_apps.rollout_restart_statefulset_data,
            data_apps.scale_statefulset_data,
            data_openshift.create_project_data,
            data_openshift.rollout_restart_deployment_config_data,
            data_olm.create_operator_group_data,
            data_olm.create_olm_subscription_data,
            data_olm.start_must_gather_data,
            data_kubevirt._vm_power_action,
            data_kubevirt.clone_virtualmachine_data,
            data_kubevirt.force_reboot_virtualmachine_data,
            data_kubevirt.create_vm_snapshot_data,
            data_kubevirt.delete_vm_snapshot_data,
        ]
        for func in audited_funcs:
            assert hasattr(func, "__wrapped__"), f"{func.__name__} is not audited"
