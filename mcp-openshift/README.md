# OpenShift Kubernetes Operations Server

A FastAPI and MCP server for operational analysis and controlled actions in Kubernetes/OpenShift clusters, including KubeVirt VirtualMachine resources.

Use:
- REST API: `/api/v1`
- MCP Streamable HTTP: `/mcp`
- Swagger/OpenAPI: `/docs`
- Health probes: `/healthz` and `/readyz`

## Features

- **Health and Discovery**:
  - `GET /`
  - `GET /healthz`
  - `GET /readyz`
- **MCP Streamable HTTP**:
  - Codex-compatible MCP endpoint at `/mcp`
  - Tools for namespaces, workloads, RBAC, routes, services, pods, events, logs, KubeVirt VMs, rollout restart, pod delete, and resource updates
- **Kubernetes Core API**: 
  - List/get namespaces
  - List/get/delete pods in a namespace
  - Read pod logs and pod/namespace events
  - List containers with images, readiness, restart counts, limits, and requests
  - List/get services
- **Kubernetes Apps API**:
  - List/get deployments
  - Request deployment rollout restart
  - Inspect deployment rollout status
  - Update deployment container CPU/memory limits and requests
- **Kubernetes Batch API**:
  - List/get CronJobs
  - List/get Jobs
- **Kubernetes RBAC API**:
  - List/get Roles and RoleBindings by namespace
  - List/get ClusterRoles and ClusterRoleBindings
- **OpenShift Route API**:
  - List/get routes via `route.openshift.io/v1`
- **KubeVirt API** (via Custom Objects):
  - List VirtualMachines in a namespace: `/namespaces/{namespace}/virtualmachines`
  - Get specific VirtualMachine: `/namespaces/{namespace}/virtualmachines/{vm_name}`

## Authentication

The server has two authentication layers:

### Client authentication for MCP and REST

Set `MCP_AUTH_TOKEN` to require clients to authenticate before they can call operational endpoints.

- Protected: `/mcp`, `/api/v1`, `/namespaces`, `/rbac`
- Public: `/`, `/docs`, `/openapi.json`, `/healthz`, `/readyz`
- Accepted headers:
  - `Authorization: Bearer <token>`
  - `X-MCP-API-Key: <token>`

If `MCP_AUTH_TOKEN` is not set, client authentication is disabled. This is convenient for local development but should not be used for a shared or public endpoint.

Generate a token:

```bash
openssl rand -hex 32
```

Run locally with authentication:

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
uvicorn main:app --host 0.0.0.0 --port 8000
```

Test the protected MCP endpoint:

```bash
curl -i http://localhost:8000/mcp
curl -i -H "Authorization: Bearer $MCP_AUTH_TOKEN" http://localhost:8000/mcp
```

### Kubernetes authentication

The server automatically handles Kubernetes authentication for calls made from the server to the cluster:

1. **In-cluster**: When running inside a Kubernetes/OpenShift pod, it uses the service account token
2. **Local development**: Falls back to your local `~/.kube/config` file

No additional configuration is needed for Kubernetes authentication.

## Requirements

- Python 3.9+
- Dependencies listed in `requirements.txt`:
  - fastapi
  - uvicorn
  - kubernetes
  - mcp

## Local Development

```bash
# Install dependencies
pip install --break-system-packages -r requirements.txt

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000

# Access the API
# Health check: http://localhost:8000/healthz
# API docs: http://localhost:8000/docs
# MCP endpoint: http://localhost:8000/mcp
```

## Codex MCP Connection

After deploying to OpenShift, connect Codex to the MCP endpoint, not the REST root.

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
codex mcp add openshift --url https://mcp-openshift-mcp-server.apps.sno.openocp.com/mcp \
  --bearer-token-env-var MCP_AUTH_TOKEN
codex mcp list
```

Alternatively, add it in `~/.codex/config.toml`:

```toml
[mcp_servers.openshift]
url = "https://mcp-openshift-mcp-server.apps.sno.openocp.com/mcp"
bearer_token_env_var = "MCP_AUTH_TOKEN"
```

The REST root remains useful for browsers and curl:

```bash
curl -k https://mcp-openshift-mcp-server.apps.sno.openocp.com/
curl -k -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  https://mcp-openshift-mcp-server.apps.sno.openocp.com/api/v1/namespaces
```

## MCP Client Configuration

Use the Streamable HTTP endpoint `/mcp` and send the same bearer token in every client.

### VS Code with GitHub Copilot

Create `.vscode/mcp.json` in your workspace:

```json
{
  "inputs": [
    {
      "id": "mcp-kubevirt-token",
      "type": "promptString",
      "description": "MCP KubeVirt token",
      "password": true
    }
  ],
  "servers": {
    "openshift-kubevirt": {
      "type": "http",
      "url": "https://mcp-openshift-mcp-server.apps.sno.openocp.com/mcp",
      "headers": {
        "Authorization": "Bearer ${input:mcp-kubevirt-token}"
      }
    }
  }
}
```

Start the server from the MCP servers view or use GitHub Copilot Chat in Agent mode.

### Claude Code

```bash
claude mcp add --transport http openshift-kubevirt \
  https://mcp-openshift-mcp-server.apps.sno.openocp.com/mcp \
  --header "Authorization: Bearer $MCP_AUTH_TOKEN"
```

Project `.mcp.json` alternative:

```json
{
  "mcpServers": {
    "openshift-kubevirt": {
      "type": "http",
      "url": "https://mcp-openshift-mcp-server.apps.sno.openocp.com/mcp",
      "headers": {
        "Authorization": "Bearer ${MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

### OpenClaw

Add a remote Streamable HTTP server to your OpenClaw config:

```json
{
  "mcp": {
    "servers": {
      "openshift-kubevirt": {
        "transport": "streamable-http",
        "url": "https://mcp-openshift-mcp-server.apps.sno.openocp.com/mcp",
        "headers": {
          "Authorization": "Bearer ${MCP_AUTH_TOKEN}"
        }
      }
    }
  }
}
```

## Container Deployment

### Helm Deployment

The Helm chart deploys the server to the `mcp-server` namespace by default:

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"

helm upgrade --install mcp-openshift ./charts/mcp-openshift \
  --namespace mcp-server \
  --create-namespace \
  --set auth.token="$MCP_AUTH_TOKEN"
```

To reuse an existing Secret:

```bash
helm upgrade --install mcp-openshift ./charts/mcp-openshift \
  --namespace mcp-server \
  --create-namespace \
  --set auth.existingSecret=mcp-openshift-auth
```

See `charts/mcp-openshift/README.md` for all chart values.

### Building the Image

The project supports multi-arch builds (ARM64 and AMD64) using Podman:

```bash
# Build for ARM64 (native on Mac M1/M2)
podman build --platform linux/arm64 -t quay.io/youruser/mcp-openshift:0.0.1-arm64 .

# Build for AMD64 (emulation)
podman build --platform linux/amd64 -t quay.io/youruser/mcp-openshift:0.0.1-amd64 .

# Create manifest list
podman manifest create quay.io/youruser/mcp-openshift:0.0.1
podman manifest add quay.io/youruser/mcp-openshift:0.0.1 quay.io/youruser/mcp-openshift:0.0.1-arm64
podman manifest add quay.io/youruser/mcp-openshift:0.0.1 quay.io/youruser/mcp-openshift:0.0.1-amd64

# Push to registry
podman manifest push quay.io/youruser/mcp-openshift:0.0.1
```

### Running in Kubernetes/OpenShift

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mcp-openshift-auth
type: Opaque
stringData:
  token: "replace-with-generated-token"
---
# Example Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-openshift-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-openshift-server
  template:
    metadata:
      labels:
        app: mcp-openshift-server
    spec:
      serviceAccountName: mcp-sa  # Create a service account with appropriate RBAC
      containers:
      - name: mcp-server
        image: quay.io/youruser/mcp-openshift:0.0.1
        ports:
        - containerPort: 8000
        env:
        - name: LOG_LEVEL
          value: "info"
        - name: MCP_AUTH_TOKEN
          valueFrom:
            secretKeyRef:
              name: mcp-openshift-auth
              key: token
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-openshift-service
spec:
  selector:
    app: mcp-openshift-server
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
  type: ClusterIP
```

Replace the sample token before applying the manifest. The server refuses known placeholder values at startup. If you already applied the sample manifest, patch the Secret and restart the deployment:

```bash
oc -n mcp-server patch secret mcp-openshift-auth \
  --type merge \
  -p "{\"stringData\":{\"token\":\"$(openssl rand -hex 32)\"}}"
oc -n mcp-server rollout restart deployment/mcp-openshift
```

### Required RBAC Permissions

Create a Role or ClusterRole with permissions to:
- `namespaces`: get, list
- `pods`: get, list, delete
- `pods/log`: get
- `events`: get, list
- `services`: get, list
- `deployments.apps`: get, list, patch
- `jobs.batch`: get, list
- `cronjobs.batch`: get, list
- `roles.rbac.authorization.k8s.io`: get, list
- `rolebindings.rbac.authorization.k8s.io`: get, list
- `clusterroles.rbac.authorization.k8s.io`: get, list
- `clusterrolebindings.rbac.authorization.k8s.io`: get, list
- `routes.route.openshift.io`: get, list (if using OpenShift)
- `virtualmachines.kubevirt.io`: get, list (if using KubeVirt)

Example Role:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: mcp-server-role
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "delete"]
- apiGroups: [""]
  resources: ["events", "services"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "patch"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list"]
- apiGroups: ["rbac.authorization.k8s.io"]
  resources: ["roles", "rolebindings"]
  verbs: ["get", "list"]
- apiGroups: ["route.openshift.io"]
  resources: ["routes"]
  verbs: ["get", "list"]
- apiGroups: ["kubevirt.io"]
  resources: ["virtualmachines"]
  verbs: ["get", "list"]
```

Namespace and cluster-wide RBAC resources require a ClusterRole:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-server-cluster-role
rules:
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["get", "list"]
- apiGroups: ["rbac.authorization.k8s.io"]
  resources: ["clusterroles", "clusterrolebindings"]
  verbs: ["get", "list"]
```

## API Endpoints

All primary REST endpoints are versioned under `/api/v1`. The previous unversioned paths are still registered for backwards compatibility, but new clients should use `/api/v1`.

### Health and Discovery
```http
GET /
GET /healthz
GET /readyz
Response: {"status": "ok"}
```

### Namespaces
```http
GET /api/v1/namespaces
Response: {"kind": "NamespaceList", "count": 1, "items": [...]}

GET /api/v1/namespaces/{namespace}
Response: Namespace details with labels, annotations, status, and conditions
```

### Pods
```http
GET /api/v1/namespaces/{namespace}/pods?label_selector=app%3Ddemo
Response: {"kind": "PodList", "count": 1, "items": [...]}

GET /api/v1/namespaces/{namespace}/pods/{pod_name}
Response: Pod summary

GET /api/v1/namespaces/{namespace}/pods/{pod_name}/logs?container=app&tail_lines=200&previous=false
Response: Pod log text

GET /api/v1/namespaces/{namespace}/pods/{pod_name}/events
Response: Array of pod events

DELETE /api/v1/namespaces/{namespace}/pods/{pod_name}
Body: {"force": false, "grace_period_seconds": 30}
Response: Delete request status
```

### Containers
```http
GET /api/v1/namespaces/{namespace}/containers?label_selector=app%3Ddemo
Response: {"kind": "ContainerList", "count": 1, "items": [...]}
```

### Events
```http
GET /api/v1/namespaces/{namespace}/events
GET /api/v1/namespaces/{namespace}/events?involved_object_name=pod-1&involved_object_kind=Pod
Response: {"kind": "EventList", "count": 1, "items": [...]}
```

### Services
```http
GET /api/v1/namespaces/{namespace}/services
Response: {"kind": "ServiceList", "count": 1, "items": [...]}

GET /api/v1/namespaces/{namespace}/services/{service_name}
Response: Service summary
```

### Deployments
```http
GET /api/v1/namespaces/{namespace}/deployments?label_selector=app%3Ddemo
Response: {"kind": "DeploymentList", "count": 1, "items": [...]}

GET /api/v1/namespaces/{namespace}/deployments/{deployment_name}
Response: Deployment summary

POST /api/v1/namespaces/{namespace}/deployments/{deployment_name}/rollout/restart
Response: Rollout restart request status

GET /api/v1/namespaces/{namespace}/deployments/{deployment_name}/rollout/status
Response: Rollout progress summary

PATCH /api/v1/namespaces/{namespace}/deployments/{deployment_name}/containers/{container_name}/resources
Body: {"limits": {"cpu": "500m", "memory": "512Mi"}, "requests": {"cpu": "250m", "memory": "256Mi"}}
Response: Updated container resource summary
```

### Jobs and CronJobs
```http
GET /api/v1/namespaces/{namespace}/jobs
GET /api/v1/namespaces/{namespace}/jobs/{job_name}
GET /api/v1/namespaces/{namespace}/cronjobs
GET /api/v1/namespaces/{namespace}/cronjobs/{cronjob_name}
Response: Batch resource summaries
```

### RBAC
```http
GET /api/v1/namespaces/{namespace}/rbac/roles
GET /api/v1/namespaces/{namespace}/rbac/roles/{role_name}
GET /api/v1/namespaces/{namespace}/rbac/rolebindings
GET /api/v1/namespaces/{namespace}/rbac/rolebindings/{role_binding_name}
GET /api/v1/rbac/clusterroles
GET /api/v1/rbac/clusterroles/{cluster_role_name}
GET /api/v1/rbac/clusterrolebindings
GET /api/v1/rbac/clusterrolebindings/{cluster_role_binding_name}
Response: RBAC rules, role refs, and subjects
```

### OpenShift Routes
```http
GET /api/v1/namespaces/{namespace}/routes
GET /api/v1/namespaces/{namespace}/routes/{route_name}
Response: Route host, target service, port, TLS, and ingress data
```

### VirtualMachines (KubeVirt)
```http
GET /api/v1/namespaces/{namespace}/virtualmachines
Response: Array of VirtualMachine objects

GET /api/v1/namespaces/{namespace}/virtualmachines/{vm_name}
Response: Single VirtualMachine object
```

## Environment Variables

Currently, the server doesn't require any specific environment variables for basic operation. Future enhancements may include:
- `LOG_LEVEL`: Control logging verbosity
- `KUBE_CONFIG_PATH`: Alternative path to kubeconfig (for local development)

## Notes

- The server uses the official Kubernetes Python client
- KubeVirt integration is done through the CustomObjectsApi since VirtualMachines are CRDs
- Error handling returns appropriate HTTP status codes:
  - 401: Kubernetes authentication failed
  - 403: Forbidden by Kubernetes RBAC
  - 404: Resource not found
  - 500: Internal server error (includes Kubernetes API error details)
- CORS is not enabled by default; add middleware if needed for browser access

## License

MIT
