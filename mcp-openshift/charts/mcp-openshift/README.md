# mcp-openshift Helm chart

Deploys the MCP OpenShift/Kubernetes/KubeVirt operations server to the `mcp-server` namespace by default.

## Install

Generate a token and install the chart:

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"

helm upgrade --install mcp-openshift ./charts/mcp-openshift \
  --namespace mcp-server \
  --create-namespace \
  --set auth.token="$MCP_AUTH_TOKEN"
```

## Use an existing Secret

```bash
oc -n mcp-server create secret generic mcp-openshift-auth \
  --from-literal=token="$(openssl rand -hex 32)"

helm upgrade --install mcp-openshift ./charts/mcp-openshift \
  --namespace mcp-server \
  --create-namespace \
  --set auth.existingSecret=mcp-openshift-auth
```

## Configure Route and MCP transport security

```bash
helm upgrade --install mcp-openshift ./charts/mcp-openshift \
  --namespace mcp-server \
  --create-namespace \
  --set auth.token="$MCP_AUTH_TOKEN" \
  --set route.host=mcp-openshift-mcp-server.apps.sno.openocp.com \
  --set-json 'mcp.allowedHosts=["mcp-openshift-mcp-server.apps.sno.openocp.com","mcp-openshift-mcp-server.apps.sno.openocp.com:*","127.0.0.1:*","localhost:*"]' \
  --set-json 'mcp.allowedOrigins=["https://mcp-openshift-mcp-server.apps.sno.openocp.com","https://mcp-openshift-mcp-server.apps.sno.openocp.com:*","http://127.0.0.1:*","http://localhost:*"]'
```

## Values

| Value | Default | Description |
| --- | --- | --- |
| `namespace.name` | `mcp-server` | Namespace used by namespaced resources |
| `namespace.create` | `true` | Create the namespace from the chart |
| `image.repository` | `quay.io/fcalomen/mcp-openshift` | Container image repository |
| `image.tag` | `0.2.2` | Container image tag |
| `auth.enabled` | `true` | Set `MCP_AUTH_TOKEN` in the deployment |
| `auth.token` | empty | Token used to create the chart-managed Secret |
| `auth.existingSecret` | empty | Existing Secret name containing the token |
| `auth.tokenKey` | `token` | Secret key for the token |
| `rbac.create` | `true` | Create ClusterRole and ClusterRoleBinding |
| `route.enabled` | `true` | Create an OpenShift Route |
| `route.host` | empty | Optional explicit Route host |
