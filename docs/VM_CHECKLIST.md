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
  pkexec /usr/libexec/netmedic/helper vpn-install --execute --json '{"port":1194,"protocol":"udp","dns":"cloudflare"}'
  sudo cp /tmp/vpn.bak /usr/lib/netmedic/scripts/openvpn-install.sh
  ```
  Expected: helper exits non-zero with an `integrity` message; no script
  runs. Restore the backup and confirm the hash again.

- [ ] **No outbound download at install.** Run the GUI/daemon without network
  access and confirm the VPN panel never invokes `curl` for the installer
  (`grep -R SCRIPT_URL` returns nothing in the installed helper).

- [ ] **VPN install/add/revoke end-to-end (Fase 3).**
  ```
  pkexec /usr/libexec/netmedic/helper vpn-install --execute --json '{"port":1194,"protocol":"udp","dns":"cloudflare","client_ipv6":false,"client":"client"}'
  pkexec /usr/libexec/netmedic/helper vpn-add-client --execute --json '{"name":"laptop"}'
  pkexec /usr/libexec/netmedic/helper vpn-revoke-client --execute --json '{"name":"laptop"}'
  ```
  Expected: install completes (service RUNNING); add creates PKI entry and delivers `.ovpn`; revoke marks client revoked. Verify the `.ovpn` lands in `~/.local/share/netmedic/vpn-clients/` mode 0600 and `artifact` is absent from journal/audit log.


## F5 — keep_auth=False for high-risk verbs

- [ ] **Re-prompt on every invocation.** Run `change-dns` and `restart-adapter`
  twice in a row within 5 minutes. Expected: polkit asks for the password
  both times (no `auth_admin_keep` window). `flush-dns` and `renew-ip` keep
  the 5-minute window (single prompt).
  ```
  pkaction --action-id com.kayab.netmedic.change-dns --verbose | grep implicit
  pkaction --action-id com.kayab.netmedic.restart-adapter --verbose | grep implicit
  ```
  Expected: `auth_admin` (not `auth_admin_keep`).

## Fase 3b — N6: perfil inicial de `install --client`

- [ ] **¿Dónde queda el perfil inicial?** Ejecuta `vpn-install` como root y comprueba
  si existe `/root/client.ovpn` (o `$HOME/client.ovpn` del usuario root). Si el
  script lo genera fuera de la gestión de la app, propón en el reporte añadir
  `--output` a `vpn-install` (Fase 3b.1) y espera aprobación; no implementes
  aún.
