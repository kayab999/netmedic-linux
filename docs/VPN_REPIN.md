# VPN Installer Re-Pin Runbook (F2)

The VPN installer is **vendored** in this repository:

```
netmedic/netmedic/data/vpn/openvpn-install.sh
```

The single trust anchor is its SHA256, stored as
`netmedic.helper_verbs.PINNED_VPN_INSTALL_SHA256`. A guardian test recomputes
the hash of the vendored file, and the root helper verifies the bytes it
reads from `/usr/lib/netmedic/scripts/openvpn-install.sh` against that
constant before staging and executing them.

Nothing is downloaded at runtime. Upstream moving does not change the
installer until this repository is re-pinned.

## When to re-pin

- You deliberately want a newer upstream behaviour and have reviewed the
  upstream diff.
- Never re-pin to silence a mismatch you do not understand: a mismatch means
  the vendored file changed (corruption, accidental edit, compromise).

## Procedure

1. Pick the upstream commit deliberately (review the diff on GitHub —
   `angristan/openvpn-install`, small focused commits preferred):
   ```bash
   PIN_COMMIT=<full-upstream-sha>
   ```
2. Fetch exactly that commit over TLS and verify it locally:
   ```bash
   curl --proto=https --tlsv1.2 --retry 3 -sSL \
     -o /tmp/openvpn-install.sh \
     "https://raw.githubusercontent.com/angristan/openvpn-install/${PIN_COMMIT}/openvpn-install.sh"
   sha256sum /tmp/openvpn-install.sh
   head -1 /tmp/openvpn-install.sh   # must be a bash shebang
   bash -n /tmp/openvpn-install.sh   # syntax check
   ```
3. Cross-check the hash from a second network/path if possible (different
   machine or the GitHub UI blob view). The hash must be identical.
4. Replace the vendored bytes **exactly**:
   ```bash
   cp /tmp/openvpn-install.sh netmedic/netmedic/data/vpn/openvpn-install.sh
   sha256sum netmedic/netmedic/data/vpn/openvpn-install.sh
   ```
5. Update all three recorded values together:
   - `PINNED_VPN_INSTALL_SHA256` in `netmedic/netmedic/helper_verbs.py`
   - the table in `netmedic/netmedic/data/vpn/PROVENANCE.md`
   - `AngristanOperator.PIN_COMMIT` (provenance/status hint only)
6. Run the guards:
   ```bash
   venv/bin/python -m pytest tests/test_f2_vendored_script.py \
     tests/test_f2_helper_script.py tests/test_angristan_operator.py -q
   ```
7. Commit the bytes, the hash and the provenance note in one commit, with
   the upstream commit in the message.

## Deployment

Re-run the policy installer so the system copy matches the new pin:

```bash
sudo ./scripts/install-polkit-policy.sh
```

The helper refuses to execute a script whose bytes do not match the pin, so
an old `/usr/lib/netmedic/scripts/openvpn-install.sh` fails closed.

## What NOT to do

- Do not edit the installer by hand; replace it with upstream bytes.
- Do not put the hash of whatever is already on disk; always re-fetch and
  verify provenance first.
- Do not delete the pin or make it caller-selectable. The pin is the
  security control.
