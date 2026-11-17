# Compliance matrix — evidence per control

| Control | Code evidence | Test evidence | Status | Gap / owner |
|---|---|---|---|---|
| Single elevation path (pkexec + fixed helper) | `system.py:_validated_pkexec`, `helper_verbs.py` | `test_f1_pkexec.py` | Implemented | None |
| Peer UID check (SO_PEERCRED) | `ipc_peer.py` | `test_ipc_peer.py` | Implemented | None |
| Session token | `ipc_security.py`, `ipc_sync_client.py` | `test_ipc.py` | Implemented | Same-UID residual risk |
| Strict confirmation boolean | `ipc_security.py` | `test_ipc_actions.py` | Implemented | None |
| MCP mutating gate | `mcp` module, `NETMEDIC_MCP_ALLOW_MUTATING` | — | Implemented | VM verify |
| AI guardrail + disruptive confirm | `ai_console.py:267` (is_disruptive + _format_args) | `docs/H6_VERIFICATION.md` | Implemented | None |
| Filesystem perms 0700/0600 | `config.py`, `audit_log.py` | `test_m3_audit.py` | Implemented | None |
| Structured audit log | `audit_log.py`, helper `_journal_result` | `test_m3_audit.py`, `test_f1_journal.py` | Implemented | None |
| Production fail-closed | `system.py` (`_allow_test_execute`) | `test_helper_verbs.py` | Implemented | None |
| medic* iface allowlist | `validators.py:validate_iface` | `test_properties.py` | Implemented | None |
| VPN script integrity (vendor + pin) | `helper_verbs.py`, `helper_main.py:_read_vpn_script` | `test_f2_*` | Implemented | VM end-to-end |
| Typed VPN verbs (no env dict) | `helper_verbs.py`, `action_catalog.py` | `test_vpn_contract.py` | Implemented | VM end-to-end |
| System-owned helper | `install-polkit-policy.sh` | `test_m7_packaging.py` | Implemented | None |
| keep_auth=False high-risk verbs | `action_catalog.py` | `test_policy_and_catalog_contract.py` | Implemented | None |
| AI supply chain (hashed lock) | — | — | **Not implemented** | Fase 7 (out of release chain) |
| Model GGUF hash in code | `pilot.py:MODEL_SHA256` | — | Implemented | Add test |
| Recoverability (change-dns/restart-adapter) | — | — | **Design only** | Fase 6 (pending approval) |
| ISO 27001 control mapping | — | — | **Not started** | Fase 8 (this doc is the seed) |
| Vulnerability disclosure process | `SECURITY.md` | — | Partial | Add coordinated-disclosure timeline |

## Key disclosure

- `support@kayabsoftware.com`, 7-day acknowledgement, coordinated disclosure preferred.
- Supported versions: 1.6.x and 1.8.x (update on release).
