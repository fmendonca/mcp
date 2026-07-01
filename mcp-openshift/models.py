"""Pydantic request models for REST and MCP tool inputs."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DeleteOptions(BaseModel):
    grace_period_seconds: Optional[int] = Field(default=None, ge=0)
    force: bool = False


class ResourceRequirementsPatch(BaseModel):
    limits: Optional[Dict[str, str]] = None
    requests: Optional[Dict[str, str]] = None


class LogQuery(BaseModel):
    container: Optional[str] = None
    tail_lines: int = Field(default=200, ge=1, le=10000)
    since_seconds: Optional[int] = Field(default=None, ge=1)
    previous: bool = False


class ScaleRequest(BaseModel):
    replicas: int = Field(ge=0, le=500)


class NamespaceCreateRequest(BaseModel):
    name: str
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None


class ProjectCreateRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None


class OperatorGroupCreateRequest(BaseModel):
    name: str = "mcp-operator-group"
    target_namespaces: Optional[List[str]] = None


class OLMSubscriptionCreateRequest(BaseModel):
    name: Optional[str] = None
    package_name: str
    channel: str = "stable"
    source: str = "redhat-operators"
    source_namespace: str = "openshift-marketplace"
    install_plan_approval: str = "Automatic"
    starting_csv: Optional[str] = None


class AMQStreamsInstallRequest(BaseModel):
    namespace: str = "openshift-operators"
    channel: str = "stable"
    source: str = "redhat-operators"
    source_namespace: str = "openshift-marketplace"
    install_plan_approval: str = "Automatic"


class OLMOperatorInstallRequest(BaseModel):
    namespace: str = "openshift-operators"
    package_name: str
    channel: str = "stable"
    source: str = "redhat-operators"
    source_namespace: str = "openshift-marketplace"
    install_plan_approval: str = "Automatic"
    subscription_name: Optional[str] = None
    starting_csv: Optional[str] = None
    create_operator_group: bool = False
    operator_group_name: str = "mcp-operator-group"
    target_namespaces: Optional[List[str]] = None


class MustGatherRequest(BaseModel):
    namespace: str = "mcp-server"
    name: Optional[str] = None
    image: Optional[str] = None
    service_account_name: str = "mcp-openshift"
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
