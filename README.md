# MCP Servers

Collection of Model Context Protocol (MCP) servers for infrastructure and platform operations.

Each server exposes both a REST API (`/api/v1`) and an MCP Streamable HTTP endpoint (`/mcp`), runs as a non-root container, and requires bearer token authentication when deployed.

## Servers

| Server | Description | Image |
|---|---|---|
| [mcp-openshift](mcp-openshift/) | Full OpenShift/Kubernetes admin (100+ tools) | `ghcr.io/fmendonca/mcp-openshift:latest` |

## Container Registry

Images are published to **GitHub Container Registry (GHCR)** and updated on every merge to `main`:

```bash
# Pull latest UBI9 image (recommended)
podman pull ghcr.io/fmendonca/mcp-openshift:latest

# Pull a specific version
podman pull ghcr.io/fmendonca/mcp-openshift:v0.0.11
```

> An Alpine-based image is also available on `quay.io/fcalomen/mcp:openshift-<version>` for users who prefer a minimal footprint.

## CI / CD

| Workflow | Trigger | Purpose |
|---|---|---|
| [Tests and Linting](.github/workflows/tests.yml) | push / PR | pytest (3.10 – 3.12), black, isort, flake8, bandit, pip-audit, Helm lint, Hadolint |
| [Release — UBI9 / GHCR](.github/workflows/release.yml) | push to `main` | build multi-arch UBI9 image, push to GHCR, create GitHub Release |

## Common Design Principles

- **Security first**: non-root containers (UID 1001), all capabilities dropped, read-only rootfs, bearer token auth, input validation, no secret values exposed
- **Multi-arch**: images built for `linux/amd64` and `linux/arm64`
- **Dual interface**: every tool is available as both an MCP tool and a REST endpoint
- **Kubernetes-native**: designed to run inside the cluster via service account tokens, with `~/.kube/config` fallback for local development
- **Graceful degradation**: OpenShift/KubeVirt CRDs return 404 with a clear message when not installed

## Versioning

Releases follow [Semantic Versioning](https://semver.org/) starting at `v0.0.3`.  
The patch version is auto-incremented on every push to `main`.  
See [RELEASE.md](RELEASE.md) for the full release and versioning process.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and the PR workflow.

To add a new MCP server:

1. Create a new directory `mcp-<name>/`
2. Add `main.py`, `requirements.txt`, `Dockerfile`, `Dockerfile.ubi9`, and `README.md`
3. Add a Helm chart in `charts/mcp-<name>/`
4. Add deploy manifests in `deploy/openshift/`
5. Update this README with the new server entry

## License

MIT
