# mcp-openshift

MCP and REST server for full administrative access to OpenShift/Kubernetes clusters.

**Version:** 0.0.11
**UBI9 image:** `ghcr.io/fmendonca/mcp-openshift:latest`
**Alpine image:** `quay.io/fcalomen/mcp:openshift-0.0.11`

[![Tests](https://github.com/fmendonca/mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/fmendonca/mcp/actions/workflows/tests.yml)
[![Release](https://github.com/fmendonca/mcp/actions/workflows/release.yml/badge.svg)](https://github.com/fmendonca/mcp/actions/workflows/release.yml)

---

## Container images

| Variant | Base | Registry | When to use |
|---|---|---|---|
| **UBI9** (recommended) | `ubi9/python-312` | `ghcr.io/fmendonca/mcp-openshift` | OpenShift, FIPS environments, enterprise |
| Alpine | `alpine:3.21` | `quay.io/fcalomen/mcp` | Minimal footprint, local dev |

```bash
# UBI9 — latest release (auto-updated on every merge to main)
podman pull ghcr.io/fmendonca/mcp-openshift:latest

# UBI9 — pin to a specific version
podman pull ghcr.io/fmendonca/mcp-openshift:v0.0.11

# Alpine
podman pull quay.io/fcalomen/mcp:openshift-0.0.11
```

---

## Features

### Kubernetes Core
| Resource | Operations |
|---|---|
| Namespaces | list, get, create |
| Nodes | list, get |
| Pods | list, get, delete, logs, events |
| Containers | list (across pods) |
| Events | list (with object filter) |
| Services | list, get |
| PersistentVolumes | list, get |
| StorageClasses | list |
| PersistentVolumeClaims | list, get |
| ConfigMaps | list, get |
| ServiceAccounts | list, get |
| ResourceQuotas | list, get |
| LimitRanges | list |

### Kubernetes Apps / Networking
| Resource | Operations |
|---|---|
| Deployments | list, get, rollout restart, scale, update container resources |
| StatefulSets | list, get, rollout restart, scale |
| DaemonSets | list, get |
| ReplicaSets | list |
| HorizontalPodAutoscalers | list, get |
| Ingresses | list, get |
| NetworkPolicies | list |

### Kubernetes Batch / RBAC
| Resource | Operations |
|---|---|
| Jobs | list, get |
| CronJobs | list, get |
| Roles / RoleBindings | list, get |
| ClusterRoles / ClusterRoleBindings | list, get |

### OpenShift-specific
| Resource | Operations |
|---|---|
| Projects | list, get, create |
| Routes | list, get |
| DeploymentConfigs | list, get, rollout restart |
| BuildConfigs | list, get |
| Builds | list, get |
| ImageStreams | list, get |
| SecurityContextConstraints | list, get |
| Users | list, get |
| Groups | list, get |
| ClusterVersion | get |
| ClusterOperators | list, get |
| MachineConfigPools | list, get |
| Machines | list |
| MachineSets | list |
| OLM Operators | install any package through OLM |
| OLM Subscriptions | list, create |
| Installed Operators (CSVs) | list |
| CatalogSources | list |
| AMQ Streams | install through OLM shortcut |
| Must-gather | start Job, read logs |

### KubeVirt
| Resource | Operations |
|---|---|
| VirtualMachines | list, get, start, stop, restart |
| VirtualMachineInstances | list, get |

---

## Authentication

### Client authentication (MCP / REST)

Set `MCP_AUTH_TOKEN` to protect all operational endpoints:

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
```

Protected prefixes: `/mcp`, `/api/v1`, `/namespaces`, `/rbac`, `/nodes`, `/projects`  
Public: `/`, `/docs`, `/openapi.json`, `/healthz`, `/readyz`

Accepted headers:
- `Authorization: Bearer <token>`
- `X-MCP-API-Key: <token>`

### Kubernetes authentication

The server automatically uses:
1. **In-cluster**: service account token when running inside a pod
2. **Local dev**: `~/.kube/config`

---

## Quick Start

### Run with Podman

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"

podman run -d \
  --name mcp-openshift \
  -e MCP_AUTH_TOKEN="$MCP_AUTH_TOKEN" \
  -e KUBECONFIG=/kube/config \
  -v ~/.kube:/kube:ro \
  -p 8000:8000 \
  ghcr.io/fmendonca/mcp-openshift:latest
```

### Run locally (development)

```bash
cd mcp-openshift
pip install -r requirements.txt

# Without auth (dev only)
uvicorn main:app --host 0.0.0.0 --port 8000

# With auth
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
uvicorn main:app --host 0.0.0.0 --port 8000
```

Endpoints:
- API docs: http://localhost:8000/docs
- MCP: http://localhost:8000/mcp
- REST: http://localhost:8000/api/v1

---

## Build images locally

### UBI9 (multi-arch via Podman)

```bash
cd mcp-openshift
podman build \
  --platform linux/amd64,linux/arm64 \
  --manifest ghcr.io/fmendonca/mcp-openshift:dev \
  -f Dockerfile.ubi9 \
  .
podman manifest push --all ghcr.io/fmendonca/mcp-openshift:dev \
  docker://ghcr.io/fmendonca/mcp-openshift:dev
```

### Alpine (multi-arch via Podman)

```bash
cd mcp-openshift
VERSION=0.0.11 ./build.sh
```

---

## Deploy to OpenShift

### Helm (recommended)

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"

helm upgrade --install mcp-openshift ./charts/mcp-openshift \
  --namespace mcp-server \
  --create-namespace \
  --set auth.token="$MCP_AUTH_TOKEN" \
  --set image.repository=ghcr.io/fmendonca/mcp-openshift \
  --set image.tag=latest
```

See [charts/mcp-openshift/README.md](charts/mcp-openshift/README.md) for all values.

### Raw manifests

```bash
TOKEN="$(openssl rand -hex 32)"

oc apply -f deploy/openshift/mcp-server.yaml

oc -n mcp-server patch secret mcp-openshift-auth \
  --type merge \
  -p "{\"stringData\":{\"token\":\"${TOKEN}\"}}"

oc -n mcp-server rollout restart deployment/mcp-openshift
```

---

## MCP Client Configuration

### Claude Code

```bash
claude mcp add --transport http openshift \
  https://<your-route>/mcp \
  --header "Authorization: Bearer $MCP_AUTH_TOKEN"
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "openshift": {
      "type": "http",
      "url": "https://<your-route>/mcp",
      "headers": {
        "Authorization": "Bearer ${MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

### VS Code / GitHub Copilot

```json
{
  "inputs": [
    { "id": "ocp-token", "type": "promptString", "description": "OpenShift MCP token", "password": true }
  ],
  "servers": {
    "openshift": {
      "type": "http",
      "url": "https://<your-route>/mcp",
      "headers": { "Authorization": "Bearer ${input:ocp-token}" }
    }
  }
}
```

### OpenAI Codex

```bash
codex mcp add openshift \
  --url https://<your-route>/mcp \
  --bearer-token-env-var MCP_AUTH_TOKEN
```

---

## Security

| Control | Details |
|---|---|
| Auth token | Never committed; always rotate via `openssl rand -hex 32` |
| Container | Runs as non-root UID 1001, all Linux capabilities dropped, privilege escalation disabled, read-only root filesystem |
| Input validation | Resource names validated with regex before reaching the Kubernetes API |
| Secret exposure | Server never exposes Kubernetes Secret values — only metadata |
| RBAC | Operational RBAC for supported actions, including broad read-only access for must-gather, `create` on namespaces, ProjectRequests, OLM Subscriptions/OperatorGroups, Jobs, `pods/exec`, and temporary DaemonSets used by must-gather |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection` on every response |
| Error messages | Kubernetes internals never leaked in error responses |
| CVE scanning | `pip-audit` and `bandit` run on every CI push |

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `MCP_AUTH_TOKEN` | Bearer token for client authentication | unset (auth disabled) |
| `MCP_ALLOWED_HOSTS` | Comma-separated allowed Host headers | `127.0.0.1:*,localhost:*,[::1]:*` |
| `MCP_ALLOWED_ORIGINS` | Comma-separated allowed CORS origins | `http://127.0.0.1:*,http://localhost:*` |

---

## REST API Reference

All endpoints are under `/api/v1`. Full interactive docs at `/docs`.

Namespace and Project names must be Kubernetes DNS labels, for example
`teste-calo`. Names with underscores, such as `teste_calo`, are rejected before
calling the cluster API.

Generic OLM installs use `/api/v1/operators/install` or the MCP tool
`install_olm_operator`. Provide `package_name`, `channel`, `source`, and
`source_namespace`; set `create_operator_group=true` when installing into a
dedicated namespace that does not already have an OperatorGroup. AMQ Streams is
available as the shortcut `install_amq_streams_operator`.

```
GET  /api/v1/namespaces
POST /api/v1/namespaces  body: {"name": "example", "labels": {}, "annotations": {}}
GET  /api/v1/namespaces/{namespace}
GET  /api/v1/nodes
GET  /api/v1/nodes/{node_name}
GET  /api/v1/namespaces/{namespace}/pods
GET  /api/v1/namespaces/{namespace}/pods/{pod_name}
GET  /api/v1/namespaces/{namespace}/pods/{pod_name}/logs
GET  /api/v1/namespaces/{namespace}/pods/{pod_name}/events
DEL  /api/v1/namespaces/{namespace}/pods/{pod_name}
GET  /api/v1/namespaces/{namespace}/containers
GET  /api/v1/namespaces/{namespace}/events
GET  /api/v1/namespaces/{namespace}/services[/{service_name}]
GET  /api/v1/persistentvolumes[/{pv_name}]
GET  /api/v1/storageclasses
GET  /api/v1/namespaces/{namespace}/persistentvolumeclaims[/{pvc_name}]
GET  /api/v1/namespaces/{namespace}/configmaps[/{cm_name}]
GET  /api/v1/namespaces/{namespace}/serviceaccounts[/{sa_name}]
GET  /api/v1/namespaces/{namespace}/resourcequotas[/{rq_name}]
GET  /api/v1/namespaces/{namespace}/limitranges
GET  /api/v1/namespaces/{namespace}/deployments[/{name}]
POST /api/v1/namespaces/{namespace}/deployments/{name}/rollout/restart
GET  /api/v1/namespaces/{namespace}/deployments/{name}/rollout/status
POST /api/v1/namespaces/{namespace}/deployments/{name}/scale  body: {"replicas": N}
PATCH /api/v1/namespaces/{namespace}/deployments/{name}/containers/{c}/resources
GET  /api/v1/namespaces/{namespace}/statefulsets[/{name}]
POST /api/v1/namespaces/{namespace}/statefulsets/{name}/rollout/restart
POST /api/v1/namespaces/{namespace}/statefulsets/{name}/scale  body: {"replicas": N}
GET  /api/v1/namespaces/{namespace}/daemonsets[/{name}]
GET  /api/v1/namespaces/{namespace}/replicasets
GET  /api/v1/namespaces/{namespace}/hpas[/{name}]
GET  /api/v1/namespaces/{namespace}/ingresses[/{name}]
GET  /api/v1/namespaces/{namespace}/networkpolicies
GET  /api/v1/namespaces/{namespace}/jobs[/{job_name}]
GET  /api/v1/namespaces/{namespace}/cronjobs[/{cronjob_name}]
GET  /api/v1/namespaces/{namespace}/rbac/roles[/{role_name}]
GET  /api/v1/namespaces/{namespace}/rbac/rolebindings[/{binding_name}]
GET  /api/v1/rbac/clusterroles[/{name}]
GET  /api/v1/rbac/clusterrolebindings[/{name}]
GET  /api/v1/namespaces/{namespace}/routes[/{name}]
GET  /api/v1/projects[/{project_name}]
POST /api/v1/projects  body: {"name": "example", "display_name": "Example", "description": "Example project"}
GET  /api/v1/namespaces/{namespace}/deploymentconfigs[/{name}]
POST /api/v1/namespaces/{namespace}/deploymentconfigs/{name}/rollout/restart
GET  /api/v1/namespaces/{namespace}/buildconfigs[/{name}]
GET  /api/v1/namespaces/{namespace}/builds[/{name}]
GET  /api/v1/namespaces/{namespace}/imagestreams[/{name}]
GET  /api/v1/securitycontextconstraints[/{name}]
GET  /api/v1/users[/{name}]
GET  /api/v1/groups[/{name}]
GET  /api/v1/clusterversion
GET  /api/v1/clusteroperators[/{name}]
GET  /api/v1/machineconfigpools[/{name}]
GET  /api/v1/namespaces/{namespace}/machines
GET  /api/v1/namespaces/{namespace}/machinesets
GET  /api/v1/namespaces/{namespace}/subscriptions
POST /api/v1/namespaces/{namespace}/subscriptions
GET  /api/v1/namespaces/{namespace}/clusterserviceversions
GET  /api/v1/namespaces/{namespace}/catalogsources
POST /api/v1/namespaces/{namespace}/operatorgroups
POST /api/v1/operators/install
POST /api/v1/operators/amq-streams
POST /api/v1/must-gather
GET  /api/v1/namespaces/{namespace}/must-gather/{job_name}/logs
GET  /api/v1/namespaces/{namespace}/virtualmachines[/{vm_name}]
PUT  /api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/start
PUT  /api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/stop
PUT  /api/v1/namespaces/{namespace}/virtualmachines/{vm_name}/restart
GET  /api/v1/namespaces/{namespace}/virtualmachineinstances[/{vmi_name}]
```

---

## Error Responses

| HTTP | Meaning |
|---|---|
| 400 | Invalid resource name or request body |
| 401 | Missing or invalid auth token |
| 403 | Kubernetes RBAC denied the operation |
| 404 | Resource or CRD not found |
| 500 | Kubernetes API error |
| 503 | Kubernetes cluster not reachable |

---

## License

MIT
