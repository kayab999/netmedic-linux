# Fases 6.1/6.2 — Recoverability and restart-adapter truth (implemented)

Root-side helper; no new verb/flag; caller supplies nothing to restore.

change-dns: one monotonic deadline, `total = --timeout` (whole verb).
`apply_deadline = start + total - R`, `rollback_deadline = start + total`,
`R = min(10s, total/3)`; every command receives only the time left in its
phase. Snapshot BOTH `ipv4.dns` and `ipv4.ignore-auto-dns` via separate
`nmcli -g` calls; validate every DNS IP (`validate_dns`); ignore-auto-dns
only `yes|no` (empty aborts); empty DNS is valid. Any snapshot
failure/timeout/unexpected value => ABORT before modifying (fail-closed).
Apply the exact argv the dry-run shows (`VerbPlan.params`, no index slicing).
On failure: restore config FIRST (idempotent), then `con up` best-effort.
Veracious result: `ok=False`; details distinguish stage plus
`config=unchanged|reverted|not-restored`; a reverted config says
"reactivation not confirmed"; a failed rollback includes the exact manual
command. One journal entry per attempt and one per rollback (pkexec_uid).

restart-adapter: down, then up; if the first up times out/fails, one final
attempt with the remaining budget. Final state from IFF_UP in
`/sys/class/net/<if>/flags` (never operstate: lo/dummy report "unknown").
Carrier is read separately; absent => unknown, not an error. `ok=True` iff
IFF_UP; the message distinguishes carrier detected / no carrier / unknown.
If the interface stays down, `ok=False` with the real state in details.

F6.2 (daemon truthfulness): the daemon does not re-derive the post-condition.
`network.py:restart_adapter` has no `ip -j/-o link` poll, no 5 s loop and no
`"UP" in stdout` text fallback. It returns `ok` = the helper's `ok` and
propagates the helper's message and details verbatim (`carrier detected`,
`no carrier`, `carrier unknown`, `not UP after restart`;
`iff_up=...; carrier=...`). Loopback (`lo`) therefore succeeds without any
operstate read: the helper reports IFF_UP with carrier unknown. Tests:
`tests/test_f6_2_restart_truth.py`.

plan_verb stays pure. Executor, clock and sysfs root are injectable. Tests:
snapshot rc/timeout/invalid, con mod failure+timeout, con up failure+timeout,
restore failure, budget exhausted in rollback, empty previous DNS,
ignore-auto-dns "no", dry-run argv == executed argv, restart retry/lo/down.

HELPER_VERSION 1.8.5. `--timeout` is the total verb deadline; the daemon waits
`timeout + IPC margin` (`system.py`). NO VERIFIED: real nmcli/ip as root ->
`docs/VM_CHECKLIST.md`.
