# Fase 6 — Recoverability of change-dns/restart-adapter (approved)

Root-side helper; no new verb/flag; caller supplies nothing to restore.

change-dns: snapshot BOTH ipv4.dns and ipv4.ignore-auto-dns via separate
`nmcli -g` calls; validate each IP (validate_dns), ignore-auto-dns yes|no;
empty DNS valid. Unexpected value or snapshot failure => ABORT before modifying
(fail-closed). Apply con mod + con up. On failure: restore config FIRST (con
mod ipv4.dns "<prev>" ipv4.ignore-auto-dns <prev>, idempotent) then con up
best-effort; config restored even if up fails. Reserve R=min(10s,total/3) for
rollback with its own deadline. Result veracious: applied / reverted to <prev> /
rollback FAILED (run manually <cmd>). One journal entry per attempt and rollback.

restart-adapter: down, up; one retry on up failure; then check real state WITHOUT
treating "unknown" as failure: check IFF_UP in /sys/class/net/<iface>/flags.
Report final state truthfully; ok=False if still down.

plan_verb stays pure. Executor injectable. Tests: failure at each step, empty
prev DNS, ignore-auto-dns "no", invalid snapshot => no con mod, budget exhausted.
Bump HELPER_VERSION; update VERBS/THREAT_MODEL/COMPLIANCE_MATRIX/CHANGELOG. Bump HELPER_VERSION; update VERBS/THREAT_MODEL/COMPLIANCE_MATRIX/CHANGELOG. NO VERIFIED: real nmcli/ip as root -> VM_CHECKLIST. STOP: implementation begins after this note is committed.
