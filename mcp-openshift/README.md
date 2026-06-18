# mcp-openshift

MCP and REST server for full administrative access to OpenShift/Kubernetes clusters.

**Version:** 0.0.3+  
**UBI9 image:** `ghcr.io/fmendonca/mcp-openshift:latest`  
**Alpine image:** `quay.io/fcalomen/mcp:openshift-0.3.1`

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
docker pull ghcr.io/fmendonca/mcp-openshift:latest

# UBI9 — pin to a specific version
docker pull ghcr.io/fmendonca/mcp-openshift:v0.0.3

# Alpine
docker pull quay.io/fcalomen/mcp:openshift-0.3.1
```

---

## Features

### Kubernetes Core
| Resource | Operations |
|---|---|
| Namespaces | list, get |
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
| Projects | list, get |
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
| OLM Subscriptions | list |
| Installed Operators (CSVs) | list |
| CatalogSources | list |

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

### Run with Docker / Podman

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"

docker run -d \
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

### UBI9 (requires Docker or Podman with buildx)

```bash
cd mcp-openshift
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f Dockerfile.ubi9 \
  -t ghcr.io/fmendonca/mcp-openshift:dev \
  --push .
```

### Alpine (multi-arch via Podman)

```bash
cd mcp-openshift
VERSION=0.3.1 ./build.sh
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
| RBAC | Principle of least privilege — `get`/`list` on sensitive resources, `delete` only on pods, `patch` on workloads for restart/scale |
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

```
GET  /api/v1/namespaces
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
GET  /api/v1/namespaces/{namespace}/clusterserviceversions
GET  /api/v1/namespaces/{namespace}/catalogsources
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
