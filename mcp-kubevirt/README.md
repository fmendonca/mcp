# Kubernetes/OpenShift MCP Server

A FastAPI-based server that provides MCP (Model Context Protocol) endpoints for interacting with Kubernetes/OpenShift APIs, including KubeVirt VirtualMachine resources.

## Features

- **Health Check**: `/health` endpoint
- **Kubernetes Core API**: 
  - List namespaces: `/namespaces`
  - List pods in a namespace: `/namespaces/{namespace}/pods`
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
- `pods`: get, list
- `virtualmachines.kubevirt.io`: get, list (if using KubeVirt)

Example Role:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: mcp-server-role
rules:
- apiGroups: [""]
  resources: ["namespaces", "pods"]
  verbs: ["get", "list"]
- apiGroups: ["kubevirt.io"]
  resources: ["virtualmachines"]
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
```

### Pods
```http
GET /namespaces/{namespace}/pods
Response: [{"name": "string", "phase": "string"}]
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