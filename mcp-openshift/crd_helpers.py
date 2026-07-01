"""Generic dispatch helpers shared by every OpenShift/OLM/KubeVirt custom
resource (CRD) backed by CustomObjectsApi. A 404 on a list call means the
CRD itself isn't installed on the cluster; a 404 on a get call means the
specific object wasn't found.
"""

from typing import Any, Dict

from fastapi import HTTPException
from kubernetes.client.rest import ApiException

from config import custom_objects
from errors import api_error, crd_not_available
from summarizers import list_response
from validation import validated_name


def _list_namespaced(
    group: str, version: str, namespace: str, plural: str, summarizer, kind: str
) -> Dict[str, Any]:
    try:
        result = custom_objects.list_namespaced_custom_object(
            group, version, validated_name(namespace), plural
        )
        return list_response(
            [summarizer(item) for item in result.get("items", [])], kind
        )
    except ApiException as e:
        if e.status == 404:
            raise crd_not_available(kind)
        raise api_error(e)


def _get_namespaced(
    group: str,
    version: str,
    namespace: str,
    plural: str,
    name: str,
    summarizer,
    not_found_msg: str,
) -> Dict[str, Any]:
    try:
        obj = custom_objects.get_namespaced_custom_object(
            group, version, validated_name(namespace), plural, validated_name(name)
        )
        return summarizer(obj)
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=not_found_msg)
        raise api_error(e)


def _list_cluster(
    group: str, version: str, plural: str, summarizer, kind: str
) -> Dict[str, Any]:
    try:
        result = custom_objects.list_cluster_custom_object(group, version, plural)
        return list_response(
            [summarizer(item) for item in result.get("items", [])], kind
        )
    except ApiException as e:
        if e.status == 404:
            raise crd_not_available(kind)
        raise api_error(e)


def _get_cluster(
    group: str, version: str, plural: str, name: str, summarizer, not_found_msg: str
) -> Dict[str, Any]:
    try:
        obj = custom_objects.get_cluster_custom_object(
            group, version, plural, validated_name(name)
        )
        return summarizer(obj)
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=not_found_msg)
        raise api_error(e)
