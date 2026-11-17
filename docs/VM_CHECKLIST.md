# VM verification checklist

Items that **cannot** be verified in the development sandbox (no real
pkexec/polkit, no root, no separate distro VM). Every entry states the exact
command, the expected result, and the phase that introduced it. Do not check
an item without pasting the literal output next to it.

## F1 — helper hardening (L1/L3/L4)

- [ ] **Policy installer from a foreign cwd (L4).**
  ```
  cd /tmp
  sudo /path/to/netmedic_linux/scripts/install-polkit-policy.sh
  ```
  Expected: no `FileNotFoundError`, installer prints `version 1.8.2`, helper
  dry-run succeeds, `pkaction --action-id com.kayab.netmedic.flush-dns` lists
  the action. Evidence: paste the output.

- [ ] **Journal attribution (L3).**
  ```
  pkexec /usr/libexec/netmedic/helper flush-dns --execute --json '{}'
  journalctl -t netmedic-helper -n 1 --no-pager
  ```
  Expected: exactly one record starting `verb=flush-dns ok=1
  pkexec_uid=<your uid>`; no second `verb=` record introduced by the message.

- [ ] **pkexec identity (L1).** On each target distro (Ubuntu 22.04/24.04):
  ```
  stat -c '%n %F uid=%u mode=%a' /usr/bin/pkexec
  ```
  Expected: `regular file uid=0` with an execute bit. A non-root-owned or
  non-regular `/usr/bin/pkexec` must make elevation fail with exit 127.


## F2 — vendored installer

- [ ] **Installed bytes match the pin.**
  ```
  sudo ./scripts/install-polkit-policy.sh
  stat -c '%n %U:%G %a' /usr/lib/netmedic/scripts/openvpn-install.sh
  sha256sum /usr/lib/netmedic/scripts/openvpn-install.sh
  ```
  Expected: `root:root 644` and SHA256
  `e0ac8731423204c671f7699003e9fb6f191be77ae15ca8e5a28031f498947a07`.

- [ ] **Helper refuses a tampered system copy (fail-closed).**
  ```
  sudo cp /usr/lib/netmedic/scripts/openvpn-install.sh /tmp/vpn.bak
  echo '# tampered' | sudo tee -a /usr/lib/netmedic/scripts/openvpn-install.sh
  pkexec /usr/libexec/netmedic/helper vpn-run-script --execute \
    --json '{"script_id":"openvpn-install","env":{}}'
  sudo cp /tmp/vpn.bak /usr/lib/netmedic/scripts/openvpn-install.sh
  ```
  Expected: helper exits non-zero with an `integrity` message; no script
  runs. Restore the backup and confirm the hash again.

- [ ] **No outbound download at install.** Run the GUI/daemon without network
  access and confirm the VPN panel never invokes `curl` for the installer
  (`grep -R SCRIPT_URL` returns nothing in the installed helper).

- [ ] **VPN install/add/revoke end-to-end (deferred to Fase 2b/3).** The current
  `env` channel is transitional and does not drive the pinned commit's
  non-interactive CLI. Do not sign this item off until Phase 3 ships the
  `install`/`client add`/`client revoke` argv verbs.

