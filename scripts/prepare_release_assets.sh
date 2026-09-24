#!/bin/bash
# Build release artifacts and generate integrity manifests (SHA256 + SBOM).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    VERSION="$(python3 -c "from netmedic import __version__; print(__version__)")"
fi

DIST_DIR="${REPO_ROOT}/dist"
mkdir -p "$DIST_DIR"

echo "--- Preparing NetMedic v${VERSION} release assets ---"

"${REPO_ROOT}/scripts/build_binary.sh"

SBOM_FILE="${DIST_DIR}/sbom-python-${VERSION}.txt"
python3 -m pip freeze > "$SBOM_FILE"
# CycloneDX (preferred for IT ingest) — best-effort if tool present
if python3 -m cyclonedx_py.client --help >/dev/null 2>&1; then
  python3 -m cyclonedx_py.client -F --format json --output "${DIST_DIR}/sbom-cyclonedx-${VERSION}.json" || true
fi

CHECKSUMS_FILE="${DIST_DIR}/SHA256SUMS"
: > "$CHECKSUMS_FILE"
(
    cd "$DIST_DIR"
    sha256sum netmedic "sbom-python-${VERSION}.txt" >> SHA256SUMS
    if [ -f "sbom-cyclonedx-${VERSION}.json" ]; then
      sha256sum "sbom-cyclonedx-${VERSION}.json" >> SHA256SUMS
    fi
    # Include helper/policy for system-install verify
    if [ -f "${REPO_ROOT}/assets/com.kayab.netmedic.policy" ]; then
      sha256sum "${REPO_ROOT}/assets/com.kayab.netmedic.policy" | sed 's|.*/|policy-com.kayab.netmedic.policy |' >> SHA256SUMS || true
    fi
)

echo "--- Release assets ready in dist/ ---"
ls -la "$DIST_DIR"/netmedic "$SBOM_FILE" "$CHECKSUMS_FILE"
cat "$CHECKSUMS_FILE"