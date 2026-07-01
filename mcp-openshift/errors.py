"""Generic Kubernetes API error mapping."""

from fastapi import HTTPException
from kubernetes.client.rest import ApiException


def api_error(
    error: ApiException, not_found_detail: str = "Resource not found"
) -> HTTPException:
    if error.status == 404:
        return HTTPException(status_code=404, detail=not_found_detail)
    if error.status == 403:
        return HTTPException(status_code=403, detail="Forbidden by Kubernetes RBAC")
    if error.status == 401:
        return HTTPException(status_code=401, detail="Kubernetes authentication failed")
    if error.status == 409:
        return HTTPException(status_code=409, detail="Resource already exists")
    return HTTPException(status_code=500, detail="Internal server error")


def crd_not_available(resource_type: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"{resource_type} API not available on this cluster (CRD not installed)",
    )
