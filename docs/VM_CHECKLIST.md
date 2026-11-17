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
