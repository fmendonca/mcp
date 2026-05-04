# Development

- Install deps: `pip install --break-system-packages -r requirements.txt` (Alpine requires this flag)
- Run server: `uvicorn main:app --host 0.0.0.0 --port 8000`
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- VM endpoints return 404 if KubeVirt not installed

# Building multi-arch images (Podman)

- ARM64: `podman build --platform linux/arm64 -t quay.io/youruser/mcp-openshift:0.0.1-arm64 .`
- AMD64: `podman build --platform linux/amd64 -t quay.io/youruser/mcp-openshift:0.0.1-amd64 .`
- Create manifest: `podman manifest create quay.io/youruser/mcp-openshift:0.0.1`
- Add ARM64: `podman manifest add quay.io/youruser/mcp-openshift:0.0.1 quay.io/youruser/mcp-openshift:0.0.1-arm64`
- Add AMD64: `podman manifest add quay.io/youruser/mcp-openshift:0.0.1 quay.io/youruser/mcp-openshift:0.0.1-amd64`
- Push: `podman manifest push quay.io/youruser/mcp-openshift:0.0.1`

# Notes

- Auth: Automatic (in-cluster → local kubeconfig fallback, no config needed)
- No tests/linting: Verify by running and hitting endpoints
- Deployment RBAC: Need get/list on namespaces, pods, virtualmachines.kubevirt.io
- No environment variables required for basic operation
- Server entrypoint: `uvicorn main:app --host 0.0.0.0 --port 8000`