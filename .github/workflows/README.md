# GitHub Actions Workflows

This directory contains automated CI/CD workflows for the mcp project.

## Workflows

### build-and-push.yml
**Purpose:** Build and push container images to registry

**Triggers:**
- Push to tags matching `v*` (e.g., `v0.3.1`)
- Manual workflow dispatch with custom version

**Steps:**
1. **Validate** - Checks version format (X.Y.Z)
2. **Test** - Runs pytest and security checks
3. **Lint** - Validates Helm chart syntax
4. **Build** - Builds multi-arch images (arm64 + amd64)
5. **Push** - Pushes to quay.io registry
6. **Release** - Creates GitHub release with image details

**Secrets Required:**
- `QUAY_USERNAME` - Quay.io username
- `QUAY_PASSWORD` - Quay.io API token

**Example Usage:**
```bash
# Automatic on tag push
git tag v0.3.1
git push origin v0.3.1

# Manual trigger (GitHub UI)
# Go to Actions > Build and Push Container Image > Run workflow
# Enter version: 0.3.1
```

### tests.yml
**Purpose:** Run tests and quality checks on every push/PR

**Triggers:**
- Push to main, develop, and feat/* branches
- Pull requests to main and develop

**Test Matrix:**
- Python 3.10, 3.11, 3.12

**Steps:**
1. **Test** - Pytest with coverage for all Python versions
2. **Security** - Bandit, pip-audit security scans
3. **Lint** - Black, isort, flake8, mypy checks
4. **Helm Lint** - Validates Helm chart
5. **Dockerfile Lint** - Hadolint container image validation

**Outputs:**
- Test results and coverage reports
- Security scan findings
- Code quality metrics

## Secrets Setup

### For build-and-push.yml

1. Generate Quay.io API token:
   - Visit https://quay.io/user/[username]/settings/
   - Create application token with "write" scope

2. Add to GitHub Secrets:
   ```bash
   # Go to Repository Settings > Secrets and variables > Actions
   QUAY_USERNAME: your-username
   QUAY_PASSWORD: your-api-token
   ```

## Local Workflow Testing

To test workflows locally before pushing:

```bash
# Install act (GitHub Actions local runner)
brew install act

# Run a specific workflow
act push -W .github/workflows/tests.yml

# Run with event payload
act workflow_dispatch -W .github/workflows/build-and-push.yml \
  -i ghcr.io/catthehacker/ubuntu:full-latest
```

## Troubleshooting

### Build fails with "Invalid VERSION format"
- Ensure tag follows semver: `vX.Y.Z` (e.g., `v0.3.1`)
- No pre-release suffixes in automated builds

### Tests timeout
- Check if Kubernetes API is accessible
- Some tests may fail in CI without k8s cluster
- Mock Kubernetes responses are used to prevent this

### Container push fails
- Verify Quay.io credentials are correct
- Check if image name is correct
- Ensure you have push permissions

### Helm lint errors
- Check `values.yaml` for syntax errors
- Ensure all template variables are referenced correctly

## Monitoring Builds

### GitHub UI
- Go to **Actions** tab in repository
- Click workflow name to see recent runs
- Click run to see detailed logs

### Command Line
```bash
# List recent workflow runs
gh run list --workflow build-and-push.yml

# View logs for a specific run
gh run view <RUN_ID> --log
```

## Performance Notes

- **Test Suite:** ~2-3 minutes (Python 3.10, 3.11, 3.12)
- **Security Scans:** ~1-2 minutes
- **Build & Push:** ~10-15 minutes (multi-arch build)

Total pipeline time: ~15-20 minutes

## Future Improvements

Potential enhancements:
- [ ] Add container image vulnerability scanning (Trivy)
- [ ] Implement Kubernetes manifest validation (kubeval)
- [ ] Add performance benchmarks
- [ ] Deploy preview environments on PR
- [ ] Automatic version bumping from conventional commits
