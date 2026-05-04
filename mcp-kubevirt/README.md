# Kubernetes/OpenShift MCP Server

A FastAPI-based server that provides MCP (Model Context Protocol) endpoints for interacting with Kubernetes/OpenShift APIs, including KubeVirt VirtualMachine resources.

## Features

- **Health Check**: `/health` endpoint
- **Kubernetes Core API**: 
  - List namespaces: `/namespaces`
  - Get namespace details: `/namespaces/{namespace}`
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

The server automatically handles Kubernetes authentication:
1. **In-cluster**: When running inside a Kubernetes/OpenShift pod, it uses the service account token
2. **Local development**: Falls back to your local `~/.kube/config` file

No additional configuration is needed for authentication.

## Requirements

- Python 3.9+
- Dependencies listed in `requirements.txt`:
  - fastapi
  - uvicorn
  - kubernetes

## Local Development

```bash
# Install dependencies
pip install --break-system-packages -r requirements.txt

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000

# Access the API
# Health check: http://localhost:8000/health
# API docs: http://localhost:8000/docs
```

## Container Deployment

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

### Health Check
```http
GET /health
Response: {"status": "ok"}
```

### Namespaces
```http
GET /namespaces
Response: [{"name": "string", "status": "string"}]

GET /namespaces/{namespace}
Response: Namespace details with labels, annotations, status, and conditions
```

### Pods
```http
GET /namespaces/{namespace}/pods
Response: Array of pod summaries with containers, resources, status, and conditions

GET /namespaces/{namespace}/pods/{pod_name}
Response: Pod summary

GET /namespaces/{namespace}/pods/{pod_name}/logs?container=app&tail_lines=200&previous=false
Response: Pod log text

GET /namespaces/{namespace}/pods/{pod_name}/events
Response: Array of pod events

DELETE /namespaces/{namespace}/pods/{pod_name}
Body: {"force": false, "grace_period_seconds": 30}
Response: Delete request status
```

### Containers
```http
GET /namespaces/{namespace}/containers
Response: Array of containers grouped by pod, including image, resources, readiness, and restarts
```

### Events
```http
GET /namespaces/{namespace}/events
Response: Array of namespace events
```

### Services
```http
GET /namespaces/{namespace}/services
Response: Array of service summaries

GET /namespaces/{namespace}/services/{service_name}
Response: Service summary
```

### Deployments
```http
GET /namespaces/{namespace}/deployments
Response: Array of deployment summaries

GET /namespaces/{namespace}/deployments/{deployment_name}
Response: Deployment summary

POST /namespaces/{namespace}/deployments/{deployment_name}/rollout/restart
Response: Rollout restart request status

GET /namespaces/{namespace}/deployments/{deployment_name}/rollout/status
Response: Rollout progress summary

PATCH /namespaces/{namespace}/deployments/{deployment_name}/containers/{container_name}/resources
Body: {"limits": {"cpu": "500m", "memory": "512Mi"}, "requests": {"cpu": "250m", "memory": "256Mi"}}
Response: Updated container resource summary
```

### Jobs and CronJobs
```http
GET /namespaces/{namespace}/jobs
GET /namespaces/{namespace}/jobs/{job_name}
GET /namespaces/{namespace}/cronjobs
GET /namespaces/{namespace}/cronjobs/{cronjob_name}
Response: Batch resource summaries
```

### RBAC
```http
GET /namespaces/{namespace}/rbac/roles
GET /namespaces/{namespace}/rbac/roles/{role_name}
GET /namespaces/{namespace}/rbac/rolebindings
GET /namespaces/{namespace}/rbac/rolebindings/{role_binding_name}
GET /rbac/clusterroles
GET /rbac/clusterroles/{cluster_role_name}
GET /rbac/clusterrolebindings
GET /rbac/clusterrolebindings/{cluster_role_binding_name}
Response: RBAC rules, role refs, and subjects
```

### OpenShift Routes
```http
GET /namespaces/{namespace}/routes
GET /namespaces/{namespace}/routes/{route_name}
Response: Route host, target service, port, TLS, and ingress data
```

### VirtualMachines (KubeVirt)
```http
GET /namespaces/{namespace}/virtualmachines
Response: Array of VirtualMachine objects

GET /namespaces/{namespace}/virtualmachines/{vm_name}
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
  - 404: Resource not found
  - 500: Internal server error (includes Kubernetes API error details)
- CORS is not enabled by default; add middleware if needed for browser access

## License

MIT
