"""Data functions for OpenShift-specific custom resources: Routes,
Projects, DeploymentConfigs, BuildConfigs/Builds, ImageStreams,
SecurityContextConstraints, Users/Groups, ClusterVersion/ClusterOperators,
and the Machine API (MachineConfigPools, Machines, MachineSets).
"""

from typing import Any, Dict, Optional

from kubernetes.client.rest import ApiException

from config import (
    MACHINE_CONFIG_GROUP,
    MACHINE_CONFIG_VERSION,
    MACHINE_GROUP,
    MACHINE_VERSION,
    OPENSHIFT_APPS_GROUP,
    OPENSHIFT_APPS_VERSION,
    OPENSHIFT_BUILD_GROUP,
    OPENSHIFT_BUILD_VERSION,
    OPENSHIFT_CONFIG_GROUP,
    OPENSHIFT_CONFIG_VERSION,
    OPENSHIFT_IMAGE_GROUP,
    OPENSHIFT_IMAGE_VERSION,
    OPENSHIFT_PROJECT_GROUP,
    OPENSHIFT_PROJECT_PLURAL,
    OPENSHIFT_PROJECT_REQUEST_PLURAL,
    OPENSHIFT_PROJECT_VERSION,
    OPENSHIFT_ROUTE_GROUP,
    OPENSHIFT_ROUTE_PLURAL,
    OPENSHIFT_ROUTE_VERSION,
    OPENSHIFT_SECURITY_GROUP,
    OPENSHIFT_SECURITY_VERSION,
    OPENSHIFT_USER_GROUP,
    OPENSHIFT_USER_VERSION,
    custom_objects,
)
from crd_helpers import _get_cluster, _get_namespaced, _list_cluster, _list_namespaced
from errors import api_error
from summarizers import (
    summarize_build,
    summarize_build_config,
    summarize_cluster_operator,
    summarize_cluster_version,
    summarize_deployment_config,
    summarize_group,
    summarize_image_stream,
    summarize_machine,
    summarize_machine_config_pool,
    summarize_machine_set,
    summarize_project,
    summarize_route,
    summarize_scc,
    summarize_user,
)
from validation import validated_dns_label, validated_name


# OpenShift Routes
def list_routes_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_ROUTE_GROUP,
        OPENSHIFT_ROUTE_VERSION,
        namespace,
        OPENSHIFT_ROUTE_PLURAL,
        summarize_route,
        "RouteList",
    )


def get_route_data(namespace: str, route_name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_ROUTE_GROUP,
        OPENSHIFT_ROUTE_VERSION,
        namespace,
        OPENSHIFT_ROUTE_PLURAL,
        route_name,
        summarize_route,
        "Route not found",
    )


# OpenShift Projects
def list_projects_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_PROJECT_GROUP,
        OPENSHIFT_PROJECT_VERSION,
        OPENSHIFT_PROJECT_PLURAL,
        summarize_project,
        "ProjectList",
    )


def get_project_data(project_name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_PROJECT_GROUP,
        OPENSHIFT_PROJECT_VERSION,
        OPENSHIFT_PROJECT_PLURAL,
        project_name,
        summarize_project,
        "Project not found",
    )


def create_project_data(
    project_name: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    name = validated_dns_label(project_name, "project")
    body = {
        "apiVersion": f"{OPENSHIFT_PROJECT_GROUP}/{OPENSHIFT_PROJECT_VERSION}",
        "kind": "ProjectRequest",
        "metadata": {"name": name},
    }
    if display_name is not None:
        body["displayName"] = display_name
    if description is not None:
        body["description"] = description

    try:
        result = custom_objects.create_cluster_custom_object(
            OPENSHIFT_PROJECT_GROUP,
            OPENSHIFT_PROJECT_VERSION,
            OPENSHIFT_PROJECT_REQUEST_PLURAL,
            body,
        )
        return {"status": "created", "project": summarize_project(result)}
    except ApiException as e:
        raise api_error(e)


# OpenShift DeploymentConfigs
def list_deployment_configs_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_APPS_GROUP,
        OPENSHIFT_APPS_VERSION,
        namespace,
        "deploymentconfigs",
        summarize_deployment_config,
        "DeploymentConfigList",
    )


def get_deployment_config_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_APPS_GROUP,
        OPENSHIFT_APPS_VERSION,
        namespace,
        "deploymentconfigs",
        name,
        summarize_deployment_config,
        "DeploymentConfig not found",
    )


def rollout_restart_deployment_config_data(namespace: str, name: str) -> Dict[str, Any]:
    path = f"/apis/apps.openshift.io/v1/namespaces/{validated_name(namespace)}/deploymentconfigs/{validated_name(name)}/instantiate"
    body = {
        "kind": "DeploymentRequest",
        "apiVersion": "apps.openshift.io/v1",
        "name": name,
        "force": True,
        "latest": True,
    }
    try:
        custom_objects.api_client.call_api(
            path,
            "POST",
            header_params={"Content-Type": "application/json"},
            body=body,
            response_types_map={200: "object", 201: "object"},
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _preload_content=False,
        )
        return {"status": "rollout_requested", "name": name, "namespace": namespace}
    except ApiException as e:
        raise api_error(e, "DeploymentConfig not found")


# OpenShift BuildConfigs / Builds
def list_build_configs_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "buildconfigs",
        summarize_build_config,
        "BuildConfigList",
    )


def get_build_config_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "buildconfigs",
        name,
        summarize_build_config,
        "BuildConfig not found",
    )


def list_builds_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "builds",
        summarize_build,
        "BuildList",
    )


def get_build_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_BUILD_GROUP,
        OPENSHIFT_BUILD_VERSION,
        namespace,
        "builds",
        name,
        summarize_build,
        "Build not found",
    )


# OpenShift ImageStreams
def list_image_streams_data(namespace: str) -> Dict[str, Any]:
    return _list_namespaced(
        OPENSHIFT_IMAGE_GROUP,
        OPENSHIFT_IMAGE_VERSION,
        namespace,
        "imagestreams",
        summarize_image_stream,
        "ImageStreamList",
    )


def get_image_stream_data(namespace: str, name: str) -> Dict[str, Any]:
    return _get_namespaced(
        OPENSHIFT_IMAGE_GROUP,
        OPENSHIFT_IMAGE_VERSION,
        namespace,
        "imagestreams",
        name,
        summarize_image_stream,
        "ImageStream not found",
    )


# OpenShift Security Context Constraints
def list_sccs_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_SECURITY_GROUP,
        OPENSHIFT_SECURITY_VERSION,
        "securitycontextconstraints",
        summarize_scc,
        "SecurityContextConstraintList",
    )


def get_scc_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_SECURITY_GROUP,
        OPENSHIFT_SECURITY_VERSION,
        "securitycontextconstraints",
        name,
        summarize_scc,
        "SecurityContextConstraint not found",
    )


# OpenShift Users / Groups
def list_users_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "users",
        summarize_user,
        "UserList",
    )


def get_user_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "users",
        name,
        summarize_user,
        "User not found",
    )


def list_groups_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "groups",
        summarize_group,
        "GroupList",
    )


def get_group_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_USER_GROUP,
        OPENSHIFT_USER_VERSION,
        "groups",
        name,
        summarize_group,
        "Group not found",
    )


# OpenShift ClusterVersion / ClusterOperators
def get_cluster_version_data() -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_CONFIG_GROUP,
        OPENSHIFT_CONFIG_VERSION,
        "clusterversions",
        "version",
        summarize_cluster_version,
        "ClusterVersion not found",
    )


def list_cluster_operators_data() -> Dict[str, Any]:
    return _list_cluster(
        OPENSHIFT_CONFIG_GROUP,
        OPENSHIFT_CONFIG_VERSION,
        "clusteroperators",
        summarize_cluster_operator,
        "ClusterOperatorList",
    )


def get_cluster_operator_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        OPENSHIFT_CONFIG_GROUP,
        OPENSHIFT_CONFIG_VERSION,
        "clusteroperators",
        name,
        summarize_cluster_operator,
        "ClusterOperator not found",
    )


# Machine Config
def list_machine_config_pools_data() -> Dict[str, Any]:
    return _list_cluster(
        MACHINE_CONFIG_GROUP,
        MACHINE_CONFIG_VERSION,
        "machineconfigpools",
        summarize_machine_config_pool,
        "MachineConfigPoolList",
    )


def get_machine_config_pool_data(name: str) -> Dict[str, Any]:
    return _get_cluster(
        MACHINE_CONFIG_GROUP,
        MACHINE_CONFIG_VERSION,
        "machineconfigpools",
        name,
        summarize_machine_config_pool,
        "MachineConfigPool not found",
    )


# Machine API
def list_machines_data(namespace: str = "openshift-machine-api") -> Dict[str, Any]:
    return _list_namespaced(
        MACHINE_GROUP,
        MACHINE_VERSION,
        namespace,
        "machines",
        summarize_machine,
        "MachineList",
    )


def list_machine_sets_data(namespace: str = "openshift-machine-api") -> Dict[str, Any]:
    return _list_namespaced(
        MACHINE_GROUP,
        MACHINE_VERSION,
        namespace,
        "machinesets",
        summarize_machine_set,
        "MachineSetList",
    )
