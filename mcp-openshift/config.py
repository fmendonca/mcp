"""Shared constants and Kubernetes/OpenShift client instances."""

import os

from kubernetes import client, config

# --- OpenShift / KubeVirt API group constants ---
OPENSHIFT_ROUTE_GROUP = "route.openshift.io"
OPENSHIFT_ROUTE_VERSION = "v1"
OPENSHIFT_ROUTE_PLURAL = "routes"

OPENSHIFT_PROJECT_GROUP = "project.openshift.io"
OPENSHIFT_PROJECT_VERSION = "v1"
OPENSHIFT_PROJECT_PLURAL = "projects"
OPENSHIFT_PROJECT_REQUEST_PLURAL = "projectrequests"

OPENSHIFT_APPS_GROUP = "apps.openshift.io"
OPENSHIFT_APPS_VERSION = "v1"

OPENSHIFT_BUILD_GROUP = "build.openshift.io"
OPENSHIFT_BUILD_VERSION = "v1"

OPENSHIFT_IMAGE_GROUP = "image.openshift.io"
OPENSHIFT_IMAGE_VERSION = "v1"

OPENSHIFT_USER_GROUP = "user.openshift.io"
OPENSHIFT_USER_VERSION = "v1"

OPENSHIFT_SECURITY_GROUP = "security.openshift.io"
OPENSHIFT_SECURITY_VERSION = "v1"

OPENSHIFT_CONFIG_GROUP = "config.openshift.io"
OPENSHIFT_CONFIG_VERSION = "v1"

MACHINE_GROUP = "machine.openshift.io"
MACHINE_VERSION = "v1beta1"

MACHINE_CONFIG_GROUP = "machineconfiguration.openshift.io"
MACHINE_CONFIG_VERSION = "v1"

OLM_GROUP = "operators.coreos.com"
OLM_VERSION = "v1alpha1"
OLM_OPERATOR_GROUP_VERSION = "v1"
DEFAULT_MUST_GATHER_IMAGE = os.getenv(
    "MUST_GATHER_IMAGE", "registry.redhat.io/openshift4/ose-must-gather-rhel9:v4.22"
)

KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
KUBEVIRT_VM_PLURAL = "virtualmachines"
KUBEVIRT_VMI_PLURAL = "virtualmachineinstances"


# --- Kubernetes client setup ---
def configure_kubernetes() -> bool:
    try:
        config.load_incluster_config()
        return True
    except config.ConfigException:
        try:
            config.load_kube_config()
            return True
        except config.ConfigException:
            return False


K8S_AVAILABLE = configure_kubernetes()
if not K8S_AVAILABLE:
    import logging as _logging

    _logging.warning(
        "Could not configure Kubernetes client - API calls will fail until a valid "
        "kubeconfig or in-cluster config is available"
    )

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
batch_v1 = client.BatchV1Api()
rbac_v1 = client.RbacAuthorizationV1Api()
networking_v1 = client.NetworkingV1Api()
autoscaling_v2 = client.AutoscalingV2Api()
storage_v1 = client.StorageV1Api()
custom_objects = client.CustomObjectsApi()
