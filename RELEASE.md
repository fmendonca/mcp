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

The app's own `APP_VERSION` is never hand-edited — it's read from an env
var baked into the image at build time via a Dockerfile build-arg, set by
CI from the version it's actually building. There's nothing to keep in
sync manually.

---

## Two pipelines, one version

Two container images are built from the same source on every release, and
both pipelines are driven off the **same** computed version:

```
push → main (paths: mcp-openshift/**)
  │
  ├─ release.yml
  │   └─ version job        ← calculates next tag (auto-increment patch)
  │   └─ build-push job     ← builds UBI9 multi-arch image, pushes to GHCR
  │   └─ publish-chart job  ← packages the Helm chart, pushes to GHCR (OCI)
  │   └─ release job        ← creates the git tag (using RELEASE_PAT, see
  │                            below) + GitHub Release
  │
  └─ (tag push vX.Y.Z, from the release job above)
      └─ build-and-push.yml
          └─ validate job       ← re-validates the version from the tag
          └─ build-and-push job ← builds Alpine multi-arch image, pushes to
                                   Quay, appends a Quay section to the same
                                   GitHub Release
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

## Why two pipelines, and why they're chained

`build-and-push.yml` (Quay/Alpine) triggers on the `vX.Y.Z` tag that
`release.yml` (GHCR/UBI9) creates — it doesn't compute its own version. This
used to be broken: tags pushed with the default `GITHUB_TOKEN` don't trigger
other workflows (GitHub's anti-recursion safeguard), so the tag push
silently never fired `build-and-push.yml`. Every Quay publish was a manual
`workflow_dispatch` until this was fixed by authenticating that tag push
with a real PAT instead (see **Secrets** below).

If you only need one image, GHCR/UBI9 is the recommended, actively-tracked
default — Quay/Alpine is a secondary, minimal-footprint option kept in sync
automatically as a side effect of the same release.

---

## Container image registry

| Variant | Dockerfile | Base image | Registry | Trigger |
|---|---|---|---|---|
| **UBI9** (recommended) | `Dockerfile.ubi9` | `ubi9/python-312` | `ghcr.io/fmendonca/mcp-openshift` | push to `main` |
| Alpine | `Dockerfile` | `alpine:3.21` | `quay.io/fcalomen/mcp:openshift-*` | the tag `release.yml` creates |

**UBI9** is the recommended production image:
- Red Hat Universal Base Image — enterprise-grade, FIPS-compatible
- Suitable for OpenShift environments with restrictive SCC policies
- Rebuilt automatically by Red Hat when CVEs are patched in the base layers

```bash
podman pull ghcr.io/fmendonca/mcp-openshift:latest
podman pull ghcr.io/fmendonca/mcp-openshift:v0.0.13
podman pull quay.io/fcalomen/mcp:openshift-0.0.13
```

---

## Helm chart registry

The chart is packaged with `helm package --version --app-version` (both set
from the same version the image build uses) and pushed to GHCR as an OCI
artifact — `Chart.yaml`'s version in source stays a static placeholder;
CI overrides it at packaging time instead of anyone hand-editing it.

```bash
helm install mcp-openshift oci://ghcr.io/fmendonca/charts/mcp-openshift \
  --version 0.0.13 --namespace mcp-server --create-namespace \
  --set auth.token="$(openssl rand -hex 32)"
```

---

## Manual release

If you need to release a specific version without auto-increment:

1. Go to **Actions → Release — Build UBI9 image & publish to GHCR**
2. Click **Run workflow**
3. Fill in `version_override` (e.g. `0.1.0`)
4. Click **Run workflow**

To (re-)publish only the Quay/Alpine image for an already-released version
(e.g. after fixing something Quay-specific), trigger
**Actions → Build and Push Container Image → Run workflow** with that
version directly — this bypasses the tag-push chain.

---

## Required permissions & secrets

| Secret / permission | Purpose | How to set |
|---|---|---|
| `GITHUB_TOKEN` (automatic) | Push to GHCR, create releases, comment on PRs | No action required — provided by Actions |
| `RELEASE_PAT` | Push the release tag with a real identity so it can trigger `build-and-push.yml` | Fine-grained PAT scoped to this repo with **Contents: Read and write**, added as a repo secret. **Falls back to `GITHUB_TOKEN` if unset** — the release still works without it, but the tag push won't trigger the Quay build automatically and you'll need to dispatch it manually (see above) |
| `QUAY_USERNAME` / `QUAY_PASSWORD` | Push images to `quay.io/fcalomen/mcp` | Quay robot account credentials, added as repo secrets |
| `packages: write` | Push images/chart to `ghcr.io` | Defined in `release.yml`'s permissions block |
| `contents: write` | Create git tags + releases | Defined in both workflows' permissions blocks |

---

## Release checklist (manual merge)

Before merging a feature branch to `main`:

- [ ] All CI checks pass (`Tests and Linting` workflow green)
- [ ] `CONTRIBUTING.md` is up to date
- [ ] PR description describes all changes

After the release workflow completes:

- [ ] GitHub Release page shows the new tag
- [ ] `ghcr.io/fmendonca/mcp-openshift:latest` is updated
- [ ] Image digest is recorded in the release notes
- [ ] `build-and-push.yml` ran automatically off the new tag (check
      **Actions** — if `RELEASE_PAT` isn't configured, this needs a manual
      `workflow_dispatch` instead)
- [ ] `quay.io/fcalomen/mcp:openshift-<version>` and the Helm chart at
      `ghcr.io/fmendonca/charts/mcp-openshift` are both updated to match

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
