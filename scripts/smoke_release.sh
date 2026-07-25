#!/usr/bin/env bash
# Release / install smoke checks (non-root). Exit non-zero on failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/netmedic${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH="${ROOT}/netmedic_ai:${PYTHONPATH}"
export NETMEDIC_TEST_MODE=1
export NETMEDIC_SKIP_POLKIT=1
export NETMEDIC_USE_HELPER=0

echo "[1/5] Version import"
python3 - <<'PY'
from netmedic import __version__
print("netmedic", __version__)
assert __version__
PY

echo "[2/5] Helper dry-run / list-verbs"
if [[ -x /usr/libexec/netmedic/helper ]]; then
  /usr/libexec/netmedic/helper --list-verbs | head -c 200
  echo
  /usr/libexec/netmedic/helper flush-dns --dry-run
else
  python3 -m netmedic.helper_main --list-verbs | head -c 200
  echo
  python3 -m netmedic.helper_main flush-dns --dry-run
  echo "(system helper not installed — using module path)"
fi

echo "[3/5] Polkit actions (if pkaction available)"
if command -v pkaction >/dev/null 2>&1; then
  count="$(pkaction 2>/dev/null | grep -c 'com.kayab.netmedic' || true)"
  echo "kayab actions visible: ${count}"
  if [[ "${count}" -lt 1 ]]; then
    echo "WARNING: no kayab polkit actions; run ./scripts/install-polkit-policy.sh"
  fi
else
  echo "pkaction not found — skip"
fi

echo "[4/5] Policy file present"
test -f assets/com.kayab.netmedic.policy

echo "[5/5] Test suite"
python3 -m pytest tests/ -q --tb=line

echo "OK: smoke_release passed"
