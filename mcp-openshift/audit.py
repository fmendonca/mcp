"""Structured audit logging for mutating operations.

Every mutating data function is wrapped with @audited("<action>") so both
surfaces that call it (REST endpoints and MCP tools) produce one JSON audit
record per invocation — what was attempted, with which scalar arguments,
when, and whether it succeeded. Records go to the "mcp_openshift.audit"
logger; ship them wherever your logging pipeline sends stdout.

Auth is a single shared bearer token, so there is no per-caller identity to
record — "who" is whoever holds the token. If per-user identity is added
later, enrich the record here.
"""

import functools
import inspect
import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

audit_logger = logging.getLogger("mcp_openshift.audit")


def _scalar_params(fn, args, kwargs):
    """The function's scalar arguments (str/int/bool/None) by name.
    Request-model objects are deliberately excluded so bodies never land
    in the audit trail.
    """
    bound = inspect.signature(fn).bind(*args, **kwargs)
    bound.apply_defaults()
    return {
        name: value
        for name, value in bound.arguments.items()
        if value is None or isinstance(value, (str, int, bool))
    }


def _emit(action, outcome, params, status_code=None):
    record = {
        "audit": True,
        "action": action,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **params,
    }
    if status_code is not None:
        record["status_code"] = status_code
    audit_logger.info(json.dumps(record, default=str))


def audited(action):
    """Wrap a mutating data function so every call emits an audit record."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            params = _scalar_params(fn, args, kwargs)
            try:
                result = fn(*args, **kwargs)
            except HTTPException as exc:
                _emit(action, "error", params, status_code=exc.status_code)
                raise
            except Exception:
                _emit(action, "error", params)
                raise
            _emit(action, "success", params)
            return result

        return wrapper

    return decorator
