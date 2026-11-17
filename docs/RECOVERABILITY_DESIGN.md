# Fase 6 — Design note: recoverability of change-dns/restart-adapter

Problem: `change-dns` (nmcli con mod + con up) and `restart-adapter` (down/up)
have no rollback; a failed `con up` leaves DNS unset or the link down.

Proposal:
- `change-dns`: snapshot the previous DNS (nmcli -g ipv4.dns), apply, run
  `con up`; on failure restore previous DNS and re-run `con up`, report final.
- `restart-adapter`: poll operstate UP (already 5s); on timeout, attempt one
  `ip link set UP` and re-poll; report final state.
- `plan_verb` stays pure (no I/O, no rollback logic in the planner).
- Rollback commands are fixed argv, allowlisted, no caller input.
- New helper verb `change-dns-rollback`? No: reuse change-dns with a
  `--restore <prev>` flag validated by the helper. Or keep rollback in daemon
  (nmcli is not privileged? it is, via helper). Decide in implementation.

Open questions (approval needed before coding):
1. Rollback in helper (privileged) or daemon (needs nmcli access)?
2. Expose `--restore` flag or a separate verb for audit clarity?
3. Timeout budget for the whole apply+verify+rollback chain?
