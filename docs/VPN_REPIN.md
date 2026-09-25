# VPN Installer Re-Pin Runbook (B-9)

The VPN operator pins the upstream Angristan installer to a commit + SHA256
(`AngristanOperator.PIN_COMMIT` / `EXPECTED_SHA256`). Upstream moves: new
commits change the script bytes, the pin stops matching, and VPN install /
status / start all fail integrity checks **by design**. This doc is the
standing maintenance obligation (12207/14764): re-pin, don't bypass.

## When to re-pin

- Integrity failures naming the current pin (`PIN_COMMIT`) after an upstream
  release you actually want (new OpenVPN/EasyRSA behavior, distro fixes).
- Never re-pin to silence a mismatch you don't understand: a mismatch with
  no upstream change means compromise or corruption — investigate first.

## Procedure

1. Pick the upstream commit deliberately (review the diff on GitHub —
   `angristan/openvpn-install`, small focused commits preferred):
   ```bash
   PIN_COMMIT=<chosen-sha>
   ```
2. Download exactly that commit over TLS and hash it:
   ```bash
   curl --proto=https --tlsv1.2 --retry 3 -sSL \
     -o /tmp/openvpn-install.sh \
     "https://raw.githubusercontent.com/angristan/openvpn-install/${PIN_COMMIT}/openvpn-install.sh"
   sha256sum /tmp/openvpn-install.sh
   head -1 /tmp/openvpn-install.sh   # must be a bash shebang
   ```
3. Cross-check the hash from a second network/path if you can (different
   machine or the GitHub UI blob view). The hash must be identical.
4. Update **both** constants together in
   `netmedic/netmedic/operators/vpn/angristan.py`:
   - `PIN_COMMIT`
   - `EXPECTED_SHA256`
   - `SCRIPT_URL` (commit segment)
5. Run the VPN + helper suites before committing:
   ```bash
   venv/bin/python -m pytest tests/test_angristan_operator.py \
     tests/test_operators.py tests/test_helper_verbs.py -q
   ```
6. Commit with both values in the message. Never commit a hash that you
   generated from a file already on disk without re-downloading it.

## What NOT to do

- Do not set `EXPECTED_SHA256` to the hash of whatever happens to be in
  `~/.local/share/netmedic/operators/openvpn-install.sh` — that file is
  user-writable and proves nothing.
- Do not delete the pin to "fix" installs. The pin is the security control.
