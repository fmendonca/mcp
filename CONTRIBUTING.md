# Contributing to mcp

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the mcp project.

## Development Setup

### Prerequisites
- Python 3.10+
- Podman (for container builds)
- Helm (for chart validation)
- Git

### Local Development Environment

1. Clone the repository:
```bash
git clone https://github.com/fmendonca/mcp.git
cd mcp
```

2. Create a Python virtual environment:
```bash
cd mcp-openshift
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

## Project Layout

`mcp-openshift/` is a flat package (not a subdirectory) so `uvicorn main:app`
and the Dockerfiles' `COPY *.py .` stay simple. Each file has one job:

| File | Responsibility |
|---|---|
| `config.py` | API group/version/plural constants, Kubernetes client instances |
| `validation.py` | Resource name validation, env-driven config helpers |
| `errors.py` | Kubernetes `ApiException` → HTTP error mapping |
| `models.py` | Pydantic request models |
| `summarizers.py` | Converts Kubernetes/OpenShift/KubeVirt API objects to JSON-safe dicts |
| `crd_helpers.py` | Generic list/get dispatch shared by ~30 custom resource types |
| `data_core.py` | Core Kubernetes resources: namespaces, nodes, pods, services, storage, configmaps, quotas |
| `data_apps.py` | Deployments, StatefulSets, DaemonSets, ReplicaSets, HPAs, Ingresses, Jobs, CronJobs, RBAC |
| `data_openshift.py` | Routes, Projects, DeploymentConfigs, Builds, ImageStreams, SCCs, Machine API |
| `data_olm.py` | OLM Subscriptions/OperatorGroups/CatalogSources, must-gather |
| `data_kubevirt.py` | KubeVirt VMs/VMIs, power actions, snapshots, DataVolumes |
| `rest_api.py` | All `@app.get/post/...` REST route registrations |
| `mcp_tools.py` | All `@mcp.tool()` MCP tool registrations |
| `metrics.py` | Prometheus `/metrics` instrumentation |
| `main.py` | Auth, FastAPI/FastMCP app assembly, middleware, health endpoints |

Every REST endpoint and every MCP tool is a thin wrapper around one function
in a `data_*.py` file — that's where the actual Kubernetes API calls and
business logic live. Neither `rest_api.py` nor `mcp_tools.py` should contain
logic beyond argument marshalling.

## Running Tests

### Unit Tests
```bash
pytest tests/ -v
```

### With Coverage Report
```bash
pytest tests/ -v --cov=. --cov-report=html
# Open htmlcov/index.html to view coverage
```

### Specific Test File
```bash
pytest tests/test_validated_name.py -v
```

Test files mirror the module split above:

| File | Covers |
|---|---|
| `test_validated_name.py` | Input validation |
| `test_auth.py` | Authentication/authorization |
| `test_crd_helpers.py` | The 4 generic CRD dispatch helpers (highest-leverage — shared by ~30 resource types) |
| `test_api_endpoints.py` | Root/health endpoints, namespace/project creation, generic error handling |
| `test_core_resources.py` | Core Kubernetes REST endpoints |
| `test_apps_batch_rbac.py` | Apps/batch/RBAC REST endpoints |
| `test_openshift_wiring.py` | OpenShift/OLM REST endpoints, auth helper, `configure_kubernetes` |
| `test_kubevirt.py` | KubeVirt REST endpoints |
| `test_mcp_tools_sweep.py` | Parametrized wiring check for every pass-through `@mcp.tool()` |
| `test_mcp_tools_special.py` | The handful of MCP tools with real logic beyond pass-through |
| `test_metrics.py` | `/metrics` endpoint and request instrumentation |

Configuration for pytest, coverage, black, isort, and mypy all live in
`pyproject.toml` — there's nothing to separately configure per tool.

## Code Quality Checks

### Format Code with Black
```bash
black *.py tests/
```

### Sort Imports with isort
```bash
isort *.py tests/
```

### Lint with Flake8
```bash
flake8 *.py
```

### Type Check with mypy
```bash
mypy *.py
```

### Security Scan
```bash
bandit -r . -ll -x tests/
pip-audit --skip-editable
```

## Building Container Images

Two variants are built from the same source, `APP_VERSION` baked in via a
Dockerfile build-arg (never hardcode a version — see `main.py`'s
`APP_VERSION` line):

### UBI9 (published to GHCR, recommended)
```bash
cd mcp-openshift
podman build --build-arg APP_VERSION=0.0.0-dev -f Dockerfile.ubi9 -t mcp-openshift:dev .
```

### Alpine multi-arch (published to Quay)
```bash
cd mcp-openshift
VERSION=0.0.0-dev ./build.sh
```

`build.sh` requires `VERSION` explicitly — there's no fallback default, on
purpose (a "helpful" default is exactly what let the image version drift
from reality for two releases before it was caught).

## Helm Chart Development

### Validate Chart
```bash
helm lint mcp-openshift/charts/mcp-openshift/
```

### Template Rendering
```bash
helm template mcp-openshift mcp-openshift/charts/mcp-openshift/ \
  --values mcp-openshift/charts/mcp-openshift/values.yaml
```

### Test Installation (requires Kubernetes cluster)
```bash
helm install mcp-test mcp-openshift/charts/mcp-openshift/ \
  --namespace mcp-test \
  --create-namespace
```

The chart is also published as an OCI artifact to
`oci://ghcr.io/fmendonca/charts/mcp-openshift` on every release — see
[RELEASE.md](RELEASE.md).

## Git Workflow

### Branch Naming
- Features: `feat/feature-name`
- Bugfixes: `fix/issue-description`
- Documentation: `docs/doc-name`
- Tests: `test/test-description`

### Commit Message Format
Follow Conventional Commits:
```
type(scope): brief description

More detailed explanation if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`

### Pull Request Process
1. Create a feature branch from `main`
2. Make changes with tests
3. Run all quality checks
4. Submit PR with clear description
5. Ensure CI/CD pipeline passes
6. Request review from maintainers

## Adding New Features

### Adding a New MCP Tool

1. Implement the data function in the matching `data_*.py` file (pick by
   resource domain — see the table above)
2. Add the REST endpoint in `rest_api.py`, calling that same data function
3. Add the MCP tool in `mcp_tools.py` with `@mcp.tool()`, also calling the
   same data function — both the REST endpoint and the MCP tool should be
   thin wrappers with no logic of their own
4. Add tests: cover the data function's behavior via the REST endpoint in
   the matching `tests/test_*.py` file, and add a case to
   `test_mcp_tools_sweep.py`'s parametrized table for the MCP tool wiring
   (or a dedicated test in `test_mcp_tools_special.py` if the tool does more
   than a 1:1 forward)
5. Update `mcp-openshift/README.md`'s feature table

### Example

```python
# data_core.py
def new_tool_data(namespace: str) -> Dict[str, Any]:
    try:
        # Implementation here
        return result
    except ApiException as e:
        raise api_error(e, "Resource not found")
```

```python
# rest_api.py
@app.get("/api/v1/namespaces/{namespace}/new-tool")
def rest_new_tool(namespace: str):
    return new_tool_data(namespace)
```

```python
# mcp_tools.py
@mcp.tool()
def new_tool(namespace: str) -> Dict[str, Any]:
    """Brief description of tool."""
    return new_tool_data(namespace)
```

## Testing Guidelines

1. Use descriptive test names
2. Test both success and failure paths
3. Mock Kubernetes API calls — never hit a real cluster in unit tests
4. Use fixtures for common setup (see `tests/conftest.py`)
5. Aim for >85% code coverage; the project currently sits around 93%

## Documentation

### README Updates
- Keep feature list up to date
- Document new endpoints
- Include usage examples

### Code Comments
Only add comments for:
- Non-obvious logic
- Security-critical sections
- Complex algorithms
- Workarounds for known issues

## Security Considerations

### Code Review Focus
- Input validation is applied
- Sensitive data is not logged
- Authentication checks are present
- RBAC permissions are correct
- Dependencies have no known vulnerabilities

### Security Scanning
All PRs must pass:
- `bandit` - Security issue detection
- `pip-audit` - Dependency vulnerability check

## Release Process

Releases are fully automated — see [RELEASE.md](RELEASE.md) for the
complete process. As a contributor, you don't need to bump any version
numbers or create tags yourself; merging to `main` is enough.

## Need Help?

- Open an [issue](https://github.com/fmendonca/mcp/issues) for bugs
- Discussions for questions and ideas
- Check existing issues before opening new ones

## Code of Conduct

Please be respectful and constructive in all interactions. This project adheres to the Contributor Covenant.

---

Happy contributing! 🚀
