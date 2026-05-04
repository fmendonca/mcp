# Development

- Install dependencies: `pip install --break-system-packages -r requirements.txt`
- Run server: `uvicorn main:app --host 0.0.0.0 --port 8000`
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- VM endpoints return 404 if KubeVirt not installed

# Building multi-arch images (Podman)

- Build ARM64: `podman build --platform linux/arm64 -t quay.io/youruser/mcp-openshift:0.0.1-arm64 .`
- Build AMD64: `podman build --platform linux/amd64 -t quay.io/youruser/mcp-openshift:0.0.1-amd64 .`
- Create manifest: `podman manifest create quay.io/youruser/mcp-openshift:0.0.1`
- Add ARM64: `podman manifest add quay.io/youruser/mcp-openshift:0.0.1 quay.io/youruser/mcp-openshift:0.0.1-arm64`
- Add AMD64: `podman manifest add quay.io/youruser/mcp-openshift:0.0.1 quay.io/youruser/mcp-openshift:0.0.1-amd64`
- Push: `podman manifest push quay.io/youruser/mcp-openshift:0.0.1`

# Notes

- Authentication: Uses in-cluster config if available, else falls back to local kubeconfig.
- No tests/linting configured; verify by running and hitting endpoints.
- Requires `--break-system-packages` for pip due to Alpine's externally managed environment.
- Server entrypoint: `uvicorn main:app --host 0.0.0.0 --port 8000` (from Dockerfile CMD)