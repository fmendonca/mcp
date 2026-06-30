# mcp-openshift Helm chart

Deploys the MCP OpenShift/Kubernetes/KubeVirt operations server to the `mcp-server` namespace by default.

## Version

| Chart | App | Default image tag |
| --- | --- | --- |
| `0.0.9` | `0.0.9` | `openshift-0.0.9` |

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
| `namespace.create` | `false` | Create a Namespace object from the chart. Keep this `false` when using `--create-namespace` or an existing namespace |
| `image.repository` | `quay.io/fcalomen/mcp` | Container image repository |
| `image.tag` | `openshift-0.0.9` | Container image tag |
| `auth.enabled` | `true` | Set `MCP_AUTH_TOKEN` in the deployment |
| `auth.token` | empty | Token used to create the chart-managed Secret |
| `auth.existingSecret` | empty | Existing Secret name containing the token |
| `auth.tokenKey` | `token` | Secret key for the token |
| `rbac.create` | `true` | Create ClusterRole and ClusterRoleBinding |
| `route.enabled` | `true` | Create an OpenShift Route |
| `route.host` | empty | Optional explicit Route host |

## RBAC scope

The chart grants read access to cluster and namespaced inventory resources, plus narrowly scoped mutating verbs for supported operations. Namespace and OpenShift Project creation require:

```yaml
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["create"]
- apiGroups: ["project.openshift.io"]
  resources: ["projectrequests"]
  verbs: ["create"]
```
