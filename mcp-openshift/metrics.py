"""Prometheus metrics: an HTTP request counter/duration histogram recorded
by middleware, exposed at /metrics in the standard exposition format.
"""

import time

from fastapi import Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "mcp_openshift_http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status_code"],
)

REQUEST_DURATION_SECONDS = Histogram(
    "mcp_openshift_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)


def _route_path(request: Request) -> str:
    """The matched route's path template (e.g. .../{namespace}/pods/{pod_name})
    rather than the raw URL, to keep label cardinality bounded. Falls back to
    the raw path for requests that didn't match a route (404s).
    """
    route = request.scope.get("route")
    return route.path if route is not None else request.url.path


async def record_request_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    path = _route_path(request)
    REQUEST_COUNT.labels(
        method=request.method, path=path, status_code=response.status_code
    ).inc()
    REQUEST_DURATION_SECONDS.labels(method=request.method, path=path).observe(duration)
    return response


def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
