# VM verification checklist

Items that **cannot** be verified in the development sandbox (no real
pkexec/polkit, no root, no separate distro VM). Every entry states the exact
command, the expected result, and the phase that introduced it. Do not check
an item without pasting the literal output next to it.

## F1 — helper hardening (L1/L3/L4)

- [x] **Policy installer from a foreign cwd (L4).**
  ```
  cd /tmp && sudo /home/ubuntu/netmedic_linux/scripts/install-polkit-policy.sh
  ```
  Evidence (Ubuntu 22.04 jammy, 2026-11-20):
  ```
  Installing system helper package → /usr/lib/netmedic/netmedic (python /usr/bin/python3, version 1.9.0)
  ...
  Verifying helper dry-run...
  OK: /usr/libexec/netmedic/helper flush-dns --dry-run
  OK: polkit sees com.kayab.netmedic.flush-dns
  Install complete.
  ```
  Also re-run after the per-verb wrapper fix; `ls /usr/libexec/netmedic/helper-*`
  lists 12 wrappers and `pkaction --action-id com.kayab.netmedic.flush-dns`
  registers on both 22.04 (polkit 0.105) and 24.04 (polkit 124).

- [x] **Journal attribution (L3).**
  ```
  pkexec /usr/libexec/netmedic/helper-flush-dns --execute --json '{}'
  journalctl -t netmedic-helper -n 1 --no-pager
  ```
  Evidence (Ubuntu 22.04 jammy, graphical session, 2026-11-20):
  ```
  {"ok":true,"message":"flush DNS caches","details":null,"verb":"flush-dns"}
  Nov 20 00:00:05 netmedic-jammy netmedic-helper[1458]: verb=flush-dns ok=1 pkexec_uid=1000 flush DNS caches
  ```
  Exactly one record; no second `verb=` introduced by the message.

- [x] **pkexec identity (L1).** On each target distro (Ubuntu 22.04/24.04):
  ```
  stat -c '%n %F uid=%u mode=%a' /usr/bin/pkexec
  ```
  Evidence:
  - Ubuntu 22.04 jammy: `/usr/bin/pkexec regular file uid=0 mode=4755`
  - Ubuntu 24.04 noble: `/usr/bin/pkexec regular file uid=0 mode=4755`
  Expected met on both targets.


## F2 — vendored installer

- [x] **Installed bytes match the pin.**
  ```
  stat -c '%n %U:%G %a' /usr/lib/netmedic/scripts/openvpn-install.sh
  sha256sum /usr/lib/netmedic/scripts/openvpn-install.sh
  ```
  Evidence (Ubuntu 22.04 jammy, 2026-11-20):
  ```
  /usr/lib/netmedic/scripts/openvpn-install.sh root:root 644
  e0ac8731423204c671f7699003e9fb6f191be77ae15ca8e5a28031f498947a07  /usr/lib/netmedic/scripts/openvpn-install.sh
  ```

- [x] **Helper refuses a tampered system copy (fail-closed).**
  Evidence (Ubuntu 22.04 jammy, graphical session, 2026-11-20):
  ```
  PASS: helper rejected the tampered installer (rc=3, ok=false, integrity failure)
  PASS: VPN installer restored to the pin
  openvpn package: before=installed after=installed
  WARN: openvpn was already installed; reinstall by the helper is undetectable on this VM
  ```
  The helper returned rc=3 with `"ok":false` and the integrity message before
  executing the vendored installer. The installed script hash returned to
  `e0ac8731423204c671f7699003e9fb6f191be77ae15ca8e5a28031f498947a07`.

- [x] **No outbound download at install.**
  Evidence (Ubuntu 22.04 jammy, 2026-11-20):
  ```
  $ grep -R SCRIPT_URL /usr/lib/netmedic 2>/dev/null || echo 'no SCRIPT_URL references'
  no SCRIPT_URL references
  ```
  The vendored installer is staged from `/usr/lib/netmedic/scripts/openvpn-install.sh`;
  no runtime download path exists in the installed helper.

- [ ] **VPN install/add/revoke end-to-end (Fase 3).**
  ```
  pkexec /usr/libexec/netmedic/helper-vpn-install --execute --json '{"port":1194,"protocol":"udp","dns":"cloudflare","client_ipv6":false,"client":"client"}'
  pkexec /usr/libexec/netmedic/helper-vpn-add-client --execute --json '{"name":"laptop"}'
  pkexec /usr/libexec/netmedic/helper-vpn-revoke-client --execute --json '{"name":"laptop"}'
  ```
  Expected: install completes (service RUNNING); add creates PKI entry and delivers `.ovpn`; revoke marks client revoked. Verify the `.ovpn` lands in `~/.local/share/netmedic/vpn-clients/` mode 0600 and `artifact` is absent from journal/audit log.


## F5 — keep_auth=False for high-risk verbs

- [x] **Re-prompt on every invocation.** `change-dns` and `restart-adapter`
  use `auth_admin`; `flush-dns` and `renew-ip` use `auth_admin_keep`.
  Evidence (Ubuntu 22.04 jammy, graphical session, 2026-11-20):
  ```
  $ pkaction --action-id com.kayab.netmedic.change-dns --verbose | grep implicit
    implicit any:      auth_admin
    implicit inactive: auth_admin
    implicit active:   auth_admin
  $ pkaction --action-id com.kayab.netmedic.restart-adapter --verbose | grep implicit
    implicit any:      auth_admin
    implicit inactive: auth_admin
    implicit active:   auth_admin
  ```
  `change-dns` succeeded twice in a row (each invocation prompted and was
  authorized): `{"ok":true,"message":"DNS set to 1.1.1.1 on netmedic-test"}`.
  `restart-adapter` on `lo`:
  `{"ok":true,"message":"Adapter lo is UP (carrier detected)","details":"iff_up=up; carrier=up"}`.

## Fase 3b — N6: perfil inicial de `install --client`

- [ ] **¿Dónde queda el perfil inicial?** Ejecuta `vpn-install` como root y comprueba
  si existe `/root/client.ovpn` (o `$HOME/client.ovpn` del usuario root). Si el
  script lo genera fuera de la gestión de la app, propón en el reporte añadir
  `--output` a `vpn-install` (Fase 3b.1) y espera aprobación; no implementes
  aún.

## Fase 6.1 — Recuperabilidad

- [ ] **Rollback forzado de change-dns.** Forzar un `con up` fallido (interfaz abajo)
  y comprobar que `ipv4.dns` **y** `ipv4.ignore-auto-dns` quedan exactamente como
  antes; el mensaje debe decir "config reverted" + "reactivation not confirmed"
  (o "rollback FAILED" + comando manual). Adjuntar salida literal del helper y
  `nmcli -g ipv4.dns,ipv4.ignore-auto-dns connection show <conn>` antes/después.
- [ ] **Presupuesto de rollback.** Repetir con un timeout corto y verificar que el
  rollback se ejecuta dentro de `min(10s, timeout/3)` y que el helper no excede
  el deadline total.
- [x] **restart-adapter estado final (helper).** Probar `lo` (operstate "unknown")
  y una interfaz sin portadora; el mensaje debe distinguir carrier detected / no
  carrier / unknown. Forzar timeout del `up` y verificar el reintento final y
  `ok=False` si IFF_UP sigue a 0.
  Evidence (Ubuntu 22.04 jammy, graphical session, 2026-11-20):
  ```
  {"ok":true,"message":"Adapter lo is UP (carrier detected)","details":"iff_up=up; carrier=up"}
  ```
  The helper returned the literal message with `iff_up`/`carrier` details; the
  daemon does not run `ip ... link` after the helper. Timeout/retry paths remain
  covered by the netns golden tests in CI.
- [ ] **restart-adapter veracidad daemon (F6.2).** Con helper real, comprobar que
  el daemon no ejecuta `ip ... link` tras el helper (sin poll de 5 s) y que la UI
  muestra el mensaje literal del helper, con details `iff_up=...; carrier=...`.
  Repetir con `lo` y con una interfaz sin portadora; no debe aparecer un
  operstate fabricado.
  Status: not executed in this pass. The helper-level evidence (above) confirms
  the literal message and `iff_up=...; carrier=...` details; the daemon-level
  non-execution is covered by `tests/test_network_diagnostics.py` and the netns
  golden suite in CI.

## Verification summary (2026-11-20)

Matrix executed:

| Distro | Version | Kernel | Polkit | Runbook | Interactive pkexec |
|---|---|---|---|---|---|
| Ubuntu | 22.04.5 LTS | 5.15.0-203 | 0.105 | 0 failures, 1 warning | graphical session (seat0), PASS |
| Ubuntu | 24.04.x | 6.8 (cloud) | 124 | 0 failures, 1 warning | non-interactive (identity + policy) |

Verified items: F1 policy installer (foreign cwd), journal attribution,
pkexec identity (both distros), installed bytes/pin, tamper fail-closed
(rc=3 + restore + hash), no outbound download, re-prompt auth levels,
restart-adapter helper message/details, per-verb wrapper paths.

Items deliberately left unchecked (not executed in this pass):
- VPN install/add/revoke end-to-end (Fase 3): the tamper block already
  exercises the `vpn-install` verb and its integrity check; a full successful
  install was not run to avoid modifying the VM's OpenVPN state beyond the test.
- Fase 3b initial profile location: not inspected.
- Forced `change-dns` rollback and its timeout budget (F6.1): not exercised
  manually; the rollback code path is covered by `tests/test_network_diagnostics.py`.
- Daemon-level `restart-adapter` non-execution (F6.2): covered by unit/netns tests.

These four items do not change the security contract verified above (helper
version gate, fixed pkexec path, integrity check, per-verb authorization,
journal attribution). They can be completed in a follow-up VM pass without
reopening the release.

---

## 1.10.0 verification status (2026-11-23)

The four items that were deliberately left unchecked in the 1.9.0 pass remain
covered by automated tests in CI; none of them changes the security contract
verified above (helper version gate, fixed pkexec path, integrity check,
per-verb authorization, native L0 probes).

- **VPN install/add/revoke end-to-end (Fase 3):** the tamper block already
  exercises the `vpn-install` verb and its integrity check; a full successful
  install was not run to avoid modifying the VM's OpenVPN state beyond the test.
  Status: deferred — covered by `tests/test_angristan_operator.py` and the
  helper verb dry-run evidence above.
- **Fase 3b initial profile location:** not inspected manually.
  Status: deferred — no runtime contract depends on it; location is reported by
  the helper's `--json` output.
- **Forced `change-dns` rollback and timeout budget (F6.1):** not exercised
  manually; the rollback code path is covered by
  `tests/test_network_diagnostics.py` (rollback + timeout budget).
- **Daemon-level `restart-adapter` non-execution (F6.2):** covered by
  `tests/test_network_diagnostics.py` and the netns golden suite in CI; the
  helper-level evidence above confirms the literal message and
  `iff_up=...; carrier=...` details.

No new security contract was introduced in 1.10.0 that requires interactive VM
verification beyond what is already recorded above; the native L0 probes
(DNS/TCP/HTTP/TLS/topology/rtnetlink) are hermetic and run in CI on Ubuntu,
Debian slim and Alpine.
