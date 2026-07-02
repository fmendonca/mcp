import contextlib
import inspect
import os
import secrets
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from kubernetes.client.rest import ApiException
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from urllib3.exceptions import MaxRetryError, NewConnectionError

# Several of these are unused directly in this module — they're re-exported
# so `from main import X` keeps working for tests/tools that reach the
# underlying client instances and helpers through the app entrypoint.
from config import apps_v1  # noqa: F401
from config import autoscaling_v2  # noqa: F401
from config import batch_v1  # noqa: F401
from config import configure_kubernetes  # noqa: F401
from config import custom_objects  # noqa: F401
from config import networking_v1  # noqa: F401
from config import rbac_v1  # noqa: F401
from config import storage_v1  # noqa: F401
from config import K8S_AVAILABLE, core_v1
from crd_helpers import _get_cluster  # noqa: F401
from crd_helpers import _get_namespaced  # noqa: F401
from crd_helpers import _list_cluster  # noqa: F401
from crd_helpers import _list_namespaced  # noqa: F401
from errors import crd_not_available  # noqa: F401
from errors import api_error
from metrics import metrics_endpoint, record_request_metrics
from validation import validated_name  # noqa: F401
from validation import csv_env

APP_VERSION = "0.0.11"

# --- Auth ---
AUTH_TOKEN_PLACEHOLDERS = {
    "replace-with-generated-token",
    "change-me",
    "changeme",
}
AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN")
if AUTH_TOKEN in AUTH_TOKEN_PLACEHOLDERS:
    raise RuntimeError("MCP_AUTH_TOKEN must be replaced with a generated secret token")

AUTH_PROTECTED_PREFIXES = (
    "/mcp",
    "/api/v1",
    "/namespaces",
    "/rbac",
    "/nodes",
    "/projects",
)


def is_authorized_request(request: Request) -> bool:
    if not AUTH_TOKEN:
        return True
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and secrets.compare_digest(token, AUTH_TOKEN):
        return True
    api_key = request.headers.get("x-mcp-api-key", "")
    return bool(api_key) and secrets.compare_digest(api_key, AUTH_TOKEN)


# ============================================================
# MCP server
# ============================================================
MCP_STATELESS_HTTP = True
MCP_JSON_RESPONSE = True
MCP_STREAMABLE_HTTP_PATH = "/"
MCP_TRANSPORT_SECURITY = TransportSecuritySettings(
    allowed_hosts=csv_env(
        "MCP_ALLOWED_HOSTS",
        ["127.0.0.1:*", "localhost:*", "[::1]:*"],
    ),
    allowed_origins=csv_env(
        "MCP_ALLOWED_ORIGINS",
        ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    ),
)


def accepted_kwargs(callable_obj: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    signature = inspect.signature(callable_obj)
    parameters = signature.parameters.values()
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in signature.parameters}


MCP_TRANSPORT_KWARGS = {
    "stateless_http": MCP_STATELESS_HTTP,
    "json_response": MCP_JSON_RESPONSE,
    "streamable_http_path": MCP_STREAMABLE_HTTP_PATH,
    "transport_security": MCP_TRANSPORT_SECURITY,
}

mcp = FastMCP(
    "OpenShift Admin Operations",
    instructions=(
        "Full administrative access to Kubernetes/OpenShift clusters. "
        "Read: namespaces, projects, nodes, pods, logs, events, containers, services, "
        "deployments, statefulsets, daemonsets, replicasets, HPAs, ingresses, network policies, "
        "jobs, cronjobs, PVs, PVCs, storage classes, config maps, service accounts, "
        "resource quotas, limit ranges, RBAC, routes, build configs, builds, image streams, "
        "SCCs, users, groups, cluster version, cluster operators, machine config pools, "
        "machines, machine sets, OLM subscriptions, installed operators, catalog sources, "
        "KubeVirt VMs and VMIs. "
        "Mutate: restart/scale deployments and statefulsets, delete pods, update resources, "
        "create namespaces/projects, install OLM operators, trigger must-gather jobs, "
        "trigger DC rollouts, start/stop/restart VMs."
    ),
    **accepted_kwargs(FastMCP, MCP_TRANSPORT_KWARGS),
)


# ============================================================
# FastAPI app
# ============================================================
@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


def create_mcp_streamable_http_app():
    return mcp.streamable_http_app(
        **accepted_kwargs(mcp.streamable_http_app, MCP_TRANSPORT_KWARGS)
    )


app = FastAPI(
    title="OpenShift Admin MCP Server",
    version=APP_VERSION,
    description=(
        "Production REST and MCP server for full OpenShift/Kubernetes administration. "
        "Use /api/v1 for REST and /mcp for MCP Streamable HTTP."
    ),
    lifespan=lifespan,
)
app.mount("/mcp", create_mcp_streamable_http_app())


@app.exception_handler(MaxRetryError)
async def max_retry_error_handler(request: Request, exc: MaxRetryError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Kubernetes cluster is not available"},
    )


@app.exception_handler(NewConnectionError)
async def new_connection_error_handler(request: Request, exc: NewConnectionError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Kubernetes cluster is not available"},
    )


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    if any(
        request.url.path.startswith(p) for p in AUTH_PROTECTED_PREFIXES
    ) and not is_authorized_request(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid authentication token"},
            headers={"WWW-Authenticate": 'Bearer realm="mcp-openshift"'},
        )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


app.middleware("http")(record_request_metrics)


@app.get("/metrics")
def metrics():
    return metrics_endpoint()


@app.get("/")
def root():
    return {
        "name": "OpenShift Admin MCP Server",
        "version": APP_VERSION,
        "rest": "/api/v1",
        "mcp": "/mcp",
        "docs": "/docs",
        "health": "/healthz",
        "ready": "/readyz",
    }


@app.get("/healthz")
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/readyz")
def ready():
    if not K8S_AVAILABLE:
        raise HTTPException(status_code=503, detail="Kubernetes client not configured")
    try:
        core_v1.get_api_resources()
        return {"status": "ready"}
    except ApiException as e:
        raise api_error(e)


# Route/tool registration side effects — must come after `app`/`mcp` exist above.
import mcp_tools  # noqa: E402,F401
import rest_api  # noqa: E402,F401

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
