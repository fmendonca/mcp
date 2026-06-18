# Release Process

This document describes how releases are created, versioned, and published for the `mcp-openshift` server.

---

## Versioning scheme

The project follows **Semantic Versioning** (`MAJOR.MINOR.PATCH`):

| Segment | When it changes |
|---|---|
| `MAJOR` | Breaking API or behaviour change |
| `MINOR` | New tools/endpoints added (backwards-compatible) |
| `PATCH` | Bug fixes, dependency updates, security patches |

Releases start at **`v0.0.3`** and are automatically incremented on every merge to `main`.

---

## Automated release workflow

Every push to `main` that touches `mcp-openshift/**` triggers the [release.yml](.github/workflows/release.yml) workflow:

```
push → main
  └─ version job      ← calculates next tag (auto-increment patch)
  └─ build-push job   ← builds UBI9 multi-arch image, pushes to GHCR
  └─ release job      ← creates git tag + GitHub Release
```

### Version calculation

```
latest git tag   →  v0.0.X
no tags found    →  v0.0.2  (so first release = v0.0.3)
next version     →  v0.0.(X+1)
```

To bump `MINOR` or `MAJOR` instead, use the **manual trigger** with `version_override`:

```
GitHub → Actions → Release workflow → Run workflow → version_override: 0.1.0
```

---

## Container image registry

Images are published to **GitHub Container Registry (GHCR)**:

| Tag | Description |
|---|---|
| `ghcr.io/fmendonca/mcp-openshift:latest` | Most recent release |
| `ghcr.io/fmendonca/mcp-openshift:v0.0.3` | Specific version |

### Image variants

| Variant | Dockerfile | Base image | Registry |
|---|---|---|---|
| **UBI9** (default) | `Dockerfile.ubi9` | `ubi9/python-312` | `ghcr.io/fmendonca/mcp-openshift` |
| Alpine | `Dockerfile` | `alpine:3.21` | `quay.io/fcalomen/mcp:openshift-*` |

**UBI9** is the recommended production image:
- Red Hat Universal Base Image — enterprise-grade, FIPS-compatible
- Suitable for OpenShift environments with restrictive SCC policies
- Rebuilt automatically by Red Hat when CVEs are patched in the base layers

---

## Manual release

If you need to release a specific version without auto-increment:

1. Go to **Actions → Release — Build UBI9 image & publish to GHCR**
2. Click **Run workflow**
3. Fill in `version_override` (e.g. `0.1.0`)
4. Click **Run workflow**

---

## Required permissions & secrets

| Secret / permission | Purpose | How to set |
|---|---|---|
| `GITHUB_TOKEN` (automatic) | Push to GHCR, create releases | No action required — provided by Actions |
| `packages: write` | Push images to `ghcr.io` | Defined in `release.yml` permissions block |
| `contents: write` | Create git tags + releases | Defined in `release.yml` permissions block |

No external secrets (Quay, Docker Hub) are needed for the GHCR-based workflow.

---

## Release checklist (manual merge)

Before merging a feature branch to `main`:

- [ ] All CI checks pass (`Tests and Linting` workflow green)
- [ ] `APP_VERSION` in `main.py` matches the intended release (or will be bumped by the release workflow)
- [ ] `CONTRIBUTING.md` is up to date
- [ ] PR description describes all changes

After the release workflow completes:

- [ ] GitHub Release page shows the new tag
- [ ] `ghcr.io/fmendonca/mcp-openshift:latest` is updated
- [ ] Image digest is recorded in the release notes

---

## Changelog format

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Meaning |
|---|---|
| `feat:` | New feature or tool |
| `fix:` | Bug or security fix |
| `docs:` | Documentation only |
| `ci:` | CI/CD workflow changes |
| `chore:` | Maintenance (deps, gitignore, etc.) |
| `refactor:` | Code restructure without behaviour change |

The changelog in each GitHub Release is auto-generated from commit messages since the previous tag.
