# Matriz de cumplimiento — evidencia por control

No afirma conformidad ni certificación. "Implementado" solo si hay test o artefacto de CI citado por ruta.

| Control | Control ISO | Evidencia (código) | Evidencia (test/CI) | Estado | Brecha / owner |
|---|---|---|---|---|---|
| Ruta única de elevación (pkexec + helper fijo) | ISO 27001 A.8.2 | `system.py:_validated_pkexec`, `helper_verbs.py` | `tests/test_f1_pkexec.py` | Implementado | — |
| Verificación de UID del par (SO_PEERCRED) | ISO 27001 A.8.2 | `ipc_peer.py` | `tests/test_ipc_peer.py` | Implementado | — |
| Token de sesión | ISO 27001 A.8.2 | `ipc_security.py`, `ipc_sync_client.py` | `tests/test_ipc.py` | Implementado | Riesgo residual mismo UID |
| Confirmación estricta (bool True) | ISO 27001 A.8.2 | `ipc_security.py` | `tests/test_ipc_actions.py` | Implementado | — |
| Gate de mutación MCP | ISO 27001 A.8.2 | módulo MCP, `NETMEDIC_MCP_ALLOW_MUTATING` | `tests/test_mcp_tools.py` | Implementado | — |
| Guardrail IA + confirmación disruptiva | ISO 42001 / 27001 A.8.2 | `ai_console.py:267` (`is_disruptive` + `_format_args`) | `docs/H6_VERIFICATION.md` (líneas citadas) | Parcial | Falta test automatizado (solo verificación documental) |
| Permisos de sistema de archivos 0700/0600 | ISO 27001 A.8.2 | `config.py`, `audit_log.py` | `tests/test_m3_audit.py` | Implementado | — |
| Registro de auditoría estructurado | ISO 27001 A.8.15 | `audit_log.py`, `_journal_result` | `tests/test_m3_audit.py`, `tests/test_f1_journal.py` | Implementado | — |
| Fail-closed en producción | ISO 27001 A.8.2 | `system.py` | `tests/test_helper_verbs.py` | Implementado | — |
| Allowlist de interfaces medic* | ISO 27001 A.8.9 | `validators.py:validate_iface` | `tests/test_properties.py` | Implementado | — |
| Integridad del script VPN (vendor + pin) | ISO 27001 A.8.25 | `helper_verbs.py`, `helper_main.py:_read_vpn_script` | `tests/test_f2_*` | Implementado | VM end-to-end pendiente |
| Verbos VPN tipados (sin dict de env) | ISO 27001 A.8.25 | `helper_verbs.py`, `action_catalog.py` | `tests/test_vpn_contract.py` | Implementado | VM end-to-end pendiente |
| Helper propiedad del sistema | ISO 27001 A.8.2 | `install-polkit-policy.sh` | `tests/test_m7_packaging.py` | Implementado | — |
| keep_auth=False en verbos de alto riesgo | ISO 27001 A.8.2 | `action_catalog.py` | `tests/test_policy_and_catalog_contract.py` | Implementado | — |
| Cadena de suministro IA (lock con hashes) | ISO 27001 A.8.28, 18974 | — | — | Brecha | Fase 7 (fuera de la cadena del release) |
| Hash del modelo GGUF en código | ISO 27001 A.8.25 | `pilot.py:MODEL_SHA256` | `tests/test_ai_model_hash.py` | Implementado | — |
| Recuperabilidad (change-dns/restart-adapter) | ISO 27001 A.8.9 | `helper_main.py:_execute_change_dns`, `_execute_restart_adapter` | `tests/test_f6_recoverability.py` (snapshot fail/timeout, mod/up fail/timeout, restore fail, budget exhausted, dry-run == exec, retry/IFF_UP/carrier); `tests/test_f6_2_restart_truth.py` (helper message/details propagated, no operstate, no text fallback) | Implementado | VM: rollback real pendiente |
| Mapeo ISO 27001 (matriz real) | ISO 27001 (anexo A) | — | — | Brecha | Esta matriz es el inicio; falta cobertura completa |
| Proceso de divulgación de vulnerabilidades | ISO 29147 / 30111 | `SECURITY.md` | — | Parcial | Añadir timeline coordinado (hecho en F8) |
| Cadena de suministro de dependencias | ISO 27001 A.8.28, 18974 | `requirements.lock` | CI `supply-chain-audit`; `tests/test_m6_supply_chain.py::test_lock_build_tools_above_cve_floor` | Implementado | Nuevas CVEs dependen del barrido semanal |

## Divulgación

- `support@kayabsoftware.com`, acuse en 7 días, divulgación coordinada (90 días).
- Versiones soportadas: solo 1.8.x. Versiones <= 1.6.0 afectadas (ver `SECURITY_ADVISORY_v1.6.1.md`).

No se afirma conformidad ni certificación.
