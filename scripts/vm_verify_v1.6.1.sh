#!/bin/bash
# NetMedic v1.6.1 Pre-Release VM Verification
# Run on clean VM with security/v1.6.1-f1-f5 checked out (e8d6d81).
set -euo pipefail
FAILURES=0
WARNINGS=0

echo "Branch:  $(git branch --show-current)"
echo "Commit:  $(git rev-parse HEAD)"
echo "Date:    $(date)"

[ "$(git branch --show-current)" = "security/v1.6.1-f1-f5" ] || { echo "WRONG BRANCH"; exit 1; }

echo "== Installing =="
sudo ./scripts/install-polkit-policy.sh

HELPER_PATH="/usr/libexec/netmedic/helper"
echo "== F3: interpreter =="
head -6 "$HELPER_PATH"
echo "$HELPER_PATH" | grep -q . || true
EXEC_LINE=$(head -6 "$HELPER_PATH" | grep -E "^exec" | head -1)
echo "Exec: $EXEC_LINE"
echo "$EXEC_LINE" | grep -q "/usr/bin/python3" || { echo "FAIL: no /usr/bin/python3"; FAILURES=$((FAILURES+1)); }
echo "$EXEC_LINE" | grep -qE '\-I\b' || { echo "FAIL: no -I"; FAILURES=$((FAILURES+1)); }
echo "$EXEC_LINE" | grep -qE '\-s\b' || { echo "WARN: no -s"; WARNINGS=$((WARNINGS+1)); }
[ "$(stat -c %U "$HELPER_PATH")" = "root" ] || { echo "FAIL: owner"; FAILURES=$((FAILURES+1)); }
echo "$EXEC_LINE" | grep -qE "venv|pyenv|conda" && { echo "FAIL: venv path"; FAILURES=$((FAILURES+1)); } || echo "PASS: no venv path"

echo "== /run =="
findmnt -no OPTIONS /run || true

echo "== F5: version =="
"$HELPER_PATH" --version || { echo "FAIL: --version"; FAILURES=$((FAILURES+1)); }

echo "== F4: policy =="
POLICY_FILE="/usr/share/polkit-1/actions/com.kayab.netmedic.policy"
grep -c "action id=" "$POLICY_FILE"
grep -c "exec.argv1" "$POLICY_FILE" || true
pkaction 2>/dev/null | grep netmedic || true
echo "Manual: run flush-dns + vpn-list, then journalctl -t polkitd | grep netmedic"

echo "== Security regression (dry-run level) =="
PYTHONPATH="$PWD/netmedic" python3 - <<'PY'
from netmedic.helper_verbs import plan_verb, VerbValidationError, PINNED_VPN_INSTALL_SHA256
for desc, fn in [
    ("attacker hash", lambda: plan_verb('vpn-run-script', {'script': '/tmp/x.sh', 'expected_sha256': 'ab'*32, 'env': {}})),
    ("LD_PRELOAD", lambda: plan_verb('vpn-run-script', {'script_id': 'openvpn-install', 'script': '/tmp/x.sh', 'expected_sha256': PINNED_VPN_INSTALL_SHA256, 'env': {'LD_PRELOAD': '/tmp/x'}})),
    ("traversal", lambda: plan_verb('vpn-list', {'index_path': '/etc/openvpn/../shadow'})),
]:
    try:
        fn()
        print(f"FAIL: {desc} accepted")
    except VerbValidationError as e:
        print(f"PASS: {desc} rejected ({e})")
PY

echo "== Tags =="
git ls-remote --tags origin | head || true

echo "Failures=$FAILURES Warnings=$WARNINGS"
[ "$FAILURES" -eq 0 ] || exit 1
echo "VM verification PASSED. Ready to tag v1.6.1."
