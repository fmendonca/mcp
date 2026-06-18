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

## Code Quality Checks

### Format Code with Black
```bash
black main.py tests/
```

### Sort Imports with isort
```bash
isort main.py tests/
```

### Lint with Flake8
```bash
flake8 main.py
```

### Type Check with mypy
```bash
mypy main.py --ignore-missing-imports
```

### Security Scan
```bash
bandit -r . -ll -x tests/
pip-audit --skip-editable
```

## Building Container Images

### Build Multi-arch Images
```bash
cd mcp-openshift
VERSION=0.3.1 ./build.sh
```

### Build Single Architecture (for testing)
```bash
podman build -t quay.io/fcalomen/mcp:openshift-0.3.1-test .
```

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
1. Implement data function in `main.py`
2. Add `@mcp.tool()` decorator
3. Add corresponding REST endpoint
4. Add tests in `tests/test_*.py`
5. Update README with new capability

### Example:
```python
@mcp.tool()
def new_tool(namespace: str) -> Dict[str, Any]:
    """Brief description of tool."""
    return new_tool_data(namespace)

def new_tool_data(namespace: str) -> Dict[str, Any]:
    try:
        # Implementation here
        return result
    except ApiException as e:
        raise api_error(e, "Resource not found")

# Also add REST endpoint
@app.get("/api/v1/namespaces/{namespace}/new-tool")
def rest_new_tool(namespace: str):
    return new_tool_data(namespace)
```

## Testing Guidelines

### Test Organization
- `test_validated_name.py` - Input validation tests
- `test_auth.py` - Authentication and authorization tests
- `test_api_endpoints.py` - REST endpoint tests
- `test_mcp_tools.py` - MCP tool tests (to be added)

### Test Best Practices
1. Use descriptive test names
2. Test both success and failure paths
3. Mock Kubernetes API calls
4. Use fixtures for common setup
5. Aim for >80% code coverage

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
- `trivy` - Container image scanning (in CI/CD)

## Release Process

### Version Numbering
Use Semantic Versioning: `MAJOR.MINOR.PATCH`

### Release Steps
1. Update version in:
   - `mcp-openshift/main.py` (APP_VERSION)
   - `mcp-openshift/Dockerfile` (image.version label)
   - `mcp-openshift/charts/mcp-openshift/Chart.yaml`
   - `mcp-openshift/README.md`

2. Commit changes:
```bash
git add -A
git commit -m "chore: bump version to X.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

3. GitHub Actions will automatically:
   - Run tests
   - Build images
   - Push to registry
   - Create release notes

## Need Help?

- Open an [issue](https://github.com/fmendonca/mcp/issues) for bugs
- Discussions for questions and ideas
- Check existing issues before opening new ones

## Code of Conduct

Please be respectful and constructive in all interactions. This project adheres to the Contributor Covenant.

---

Happy contributing! 🚀
