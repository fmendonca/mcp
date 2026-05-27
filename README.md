# MCP Servers

Collection of Model Context Protocol (MCP) servers for infrastructure and platform operations.

Each server exposes both a REST API (`/api/v1`) and a MCP Streamable HTTP endpoint (`/mcp`), runs as a non-root container, and requires bearer token authentication when deployed.

## Servers

| Server | Description | Image |
|---|---|---|
| [mcp-openshift](mcp-openshift/) | Full OpenShift/Kubernetes admin (75+ tools) | `quay.io/fcalomen/mcp:openshift-0.3.0` |

## Common Design Principles

- **Security first**: non-root containers, all capabilities dropped, read-only rootfs, bearer token auth, input validation, no secret values exposed
- **Multi-arch**: images built for `linux/arm64` and `linux/amd64` via Podman manifests
- **Dual interface**: every tool is available as both an MCP tool and a REST endpoint
- **Kubernetes-native**: designed to run inside the cluster using service account tokens, with local `~/.kube/config` fallback for development
- **Graceful degradation**: OpenShift/KubeVirt CRDs return 404 with a clear message when not installed

## Registry

All images are published to `quay.io/fcalomen/mcp` with the tag format `<server>-<version>`:

```
quay.io/fcalomen/mcp:openshift-0.3.0
```

## Building Images

Each server directory contains a `build.sh` that builds arm64 + amd64 with Podman and pushes a multi-arch manifest:

```bash
cd mcp-openshift
VERSION=0.3.0 ./build.sh
```

## Contributing

To add a new MCP server:

1. Create a new directory `mcp-<name>/`
2. Add `main.py`, `requirements.txt`, `Dockerfile`, `build.sh`, and `README.md`
3. Add a Helm chart in `charts/mcp-<name>/`
4. Add deploy manifests in `deploy/openshift/`
5. Update this README with the new server entry

## License

MIT
