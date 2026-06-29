#!/usr/bin/env bash
# Build and push multi-arch (arm64 + amd64) image to quay.io/fcalomen/mcp
set -euo pipefail

VERSION="${VERSION:-0.3.1}"

# Validate version format
if [[ ! $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: Invalid VERSION format (use X.Y.Z)" >&2
  exit 1
fi

REGISTRY="quay.io/fcalomen"
IMAGE="${REGISTRY}/mcp:openshift-${VERSION}"
ARM_TAG="${IMAGE}-arm64"
AMD_TAG="${IMAGE}-amd64"

echo "==> Building ${IMAGE} for linux/arm64 and linux/amd64"

podman build --platform linux/arm64 -t "${ARM_TAG}" .
echo "    arm64 done: ${ARM_TAG}"

podman build --platform linux/amd64 -t "${AMD_TAG}" .
echo "    amd64 done: ${AMD_TAG}"

case "$(uname -m)" in
  x86_64|amd64)
    TEST_TAG="${AMD_TAG}"
    ;;
  arm64|aarch64)
    TEST_TAG="${ARM_TAG}"
    ;;
  *)
    TEST_TAG="${AMD_TAG}"
    ;;
esac

echo "==> Smoke testing ${TEST_TAG} with an arbitrary OpenShift UID"
podman run --rm --user 12345 --entrypoint python3 "${TEST_TAG}" -c \
  "import os; assert os.access('/app', os.X_OK); assert os.access('/app/main.py', os.R_OK); import main; assert hasattr(main, 'app')"

echo "==> Pushing platform images"
podman push "${ARM_TAG}"
podman push "${AMD_TAG}"

echo "==> Creating manifest ${IMAGE}"
podman manifest rm "${IMAGE}" 2>/dev/null || true
podman manifest create "${IMAGE}"
podman manifest add "${IMAGE}" "${ARM_TAG}"
podman manifest add "${IMAGE}" "${AMD_TAG}"

echo "==> Pushing manifest"
podman manifest push --all "${IMAGE}" "docker://${IMAGE}"

echo "==> Done: ${IMAGE}"
