# VERBS.md — Tabla Maestra de Verbos y Contrato de Éxito

> **Regla de oro: exit 0 ≠ problema resuelto.** Este documento es el contrato vivo
> entre `helper_verbs.py`, `action_catalog.py`, la UI y el usuario: declara, para
> cada verbo, qué verifica el código *después* del exit 0 y qué no.

Estado: post-sweep PR1–PR6 · Semántica: `ResultCode` (models.py:8) · Mantener en cada PR.

---

## 1. Reglas de mantenimiento

1. **Verbo nuevo = fila nueva en el mismo PR.** Sin excepciones.
2. Cada verbo declara una de dos cosas:
   - **Post-condición** implementada (comando + file:line), o
   - Tag **`unverified-by-design`** con justificación de por qué es aceptable.
3. El test guardián `tests/test_verbs_doc.py` rompe el build si:
   - un verbo del catálogo no tiene fila aquí (doc faltante),
   - una fila referencia un verbo inexistente (doc drift),
   - un verbo sin post-condición carece del tag.
4. Cambiar la semántica de éxito de un verbo es un **cambio de contrato**:
   CHANGELOG + actualización de test en el mismo PR.
5. Toda reparación debe ser **reproducible a mano** con los comandos de §4.

## 2. Leyenda — ResultCode y qué ve el usuario

| Code | Icono | Significado honesto |
|---|---|---|
| OK | ✅ | Ejecutado **y verificado** (la post-condición pasó) |
| EXECUTED | ⚠️ | Exit 0; efecto aún no verificado |
| PARTIAL | ⚠️ | Verificado parcialmente (p.ej. DNS restaurado, WAN no) |
| FAILED | ❌ | El objetivo falló (verificado, o el comando falló) |
| SKIPPED | ⏭️ | Omitido con causa explícita al usuario |
| ERROR | ❌ | Error de ejecución o de entorno |
| CANCELLED | ⚠️ | El usuario canceló la autenticación (no es fallo) |

**Shim compat:** `NetResult.success` derivado de `code` solo para IPC legacy. Mapping documentado:

| code | success |
|---|---|
| OK / EXECUTED | True — doc: *"acción ejecutada; objetivo NO verificado"* |
| PARTIAL / FAILED / ERROR / SKIPPED / CANCELLED | False |

Consumidores in-repo (`tools/netmedic_mcp.py`, `netmedic_ai/toolkit.py:48`) deben migrar a `code`. `success` deprecado, remover en próxima minor.

## 3. Tabla maestra

### 3.1 Diagnóstico — seguras, sin elevación

| Verbo IPC | Comando real | Post-condición | Semántica de éxito |
|---|---|---|---|
| `network_status` | `probes.py:12-68` — DNS: `getent` ×2 hosts · Internet: ThreadPool `curl 1.1.1.1:80` + `8.8.8.8:80`, fallback `https://1.1.1.1:443`; ICMP recorded in `per[]` only (`probes.py:64-68` returns `overall_ok=False`) · captive hint if `gw_ok and not net_ok` (`network.py:304`, even when DNS “succeeds”) · NM `networking connectivity` divergence `probes.py:check_nm_connectivity` (skipped in netns) | ✅ multi-target, per-probe en `details` + `nm_divergence` | OK exige **≥1 probe TCP**; ICMP solo en `details` (§6); PARTIAL when TCP fail + ICMP ok |
| `wifi_diagnostics` | `nmcli --json device wifi list` (`operators/wifi.py:382`) | ✅ lista vacía ≠ error | OK si el scan parsea |

### 3.2 Reparación básica (Smart Repair)

| Verbo helper | Comando real | Post-condición | Semántica de éxito |
|---|---|---|---|
| `flush-dns` (`helper_verbs.py:122`) | `resolvectl flush-caches` | ⚠️ verificada **solo dentro del flujo Smart Repair** (post-diag); standalone queda EXECUTED | Standalone: "cache flushed" sin promesa de DNS |
| `renew-ip` nmcli (`helper_verbs.py:128`) | `nmcli device reapply <iface>` | ✅ `ip -4 addr` before/after + ping gw (`network.py:405-422`) → `details{old_ip,new_ip,changed,gateway_ok}` | "IP changed .10→.11" o **"retained (lease reapplied)"** — nunca "renewed" a secas |
| `renew-ip` dhclient (`helper_verbs.py:134`) | `dhclient -r` + `dhclient <iface>` | `unverified-by-design` — path de fallback raramente ejercitado; dhclient compite con NM; nunca auto-escalar (§6) | Igual que arriba si se ejecuta |
| `change-dns` (`helper_verbs.py:145`) | `nmcli con mod … ipv4.dns … ignore-auto-dns yes` + `nmcli con up` | `unverified-by-design` (pendiente) — modifica perfil NM; verificación natural = re-run `network_status` (§6) | "DNS profile changed" sin promesa de resolución |

### 3.3 Infraestructura privilegiada

| Verbo helper | Comando real | Post-condición | Semántica de éxito |
|---|---|---|---|
| `restart-adapter` (`helper_verbs.py:166`) | `ip link set <iface> down` + `up` | ✅ `ip -j link show` operstate UP, poll 5s (`network.py:546`) | OK = link realmente UP |
| `reset-stack` (`helper_verbs.py:177`) | `systemctl restart NetworkManager` | ✅ `nmcli general status`, poll 15s (`network.py:498`) | OK = NM operativo |
| `toggle-firewall` (`helper_verbs.py:184`) | `ufw --force enable` / `disable` | ✅ `get_firewall_status()` expected vs final (`network.py:415-429`) | OK = estado verificado — **positive control del audit** |

### 3.4 VPN (Angristan operator)

| Verbo helper | Comando real | Post-condición | Semántica de éxito |
|---|---|---|---|
| `vpn-run-script` (install/create/revoke) (`helper_verbs.py:209`) | script sellado `/run/netmedic/sealed.sh` con env vars | ✅ SHA256 doble (download + helper), post-op: `check_status` RUNNING + PKI index (`angristan.py:237/318/340`) | OK = servicio/PKI verificado — **modelo a replicar** |
| `vpn-start-service` / `vpn-restart-service` (`helper_verbs.py:198`) | `systemctl start/restart openvpn-server@…` | ✅ `is_service_active()` (`angristan.py:360/377`) | OK = servicio activo |
| `vpn-list-clients` (`helper_verbs.py:192`) | `cat …/pki/index.txt` | ✅ (read-only informativo) | OK = lista parseada |

### 3.5 Internos / lifecycle

| Verbo helper | Comando real | Post-condición |
|---|---|---|
| `iface-del` / `iface-add-dummy` (`helper_verbs.py:235/239`) | `ip link del/add medicXXXXXX` | ✅ allowlist `medic[0-9a-f]{6}` + reap de estado huérfano (`network.py:103-106`) |

## 4. Repro manual de verbos clave

**`network_status`** (lo que el usuario puede correr a mano para verificar):
```
ip route show default
ping -c2 -W1 <gateway>
getent hosts google.com && getent hosts cloudflare.com
curl -Is http://1.1.1.1 --connect-timeout 5
curl -Is http://8.8.8.8 --connect-timeout 5
curl -Is https://1.1.1.1 --connect-timeout 5
```

**`renew-ip`**:
```
ip -4 addr show <iface>; nmcli device reapply <iface>
sleep 2; ip -4 addr show <iface>; ping -c2 <gateway>
```

**`flush-dns`**: `resolvectl flush-caches && getent hosts google.com`

## 5. Flujo compuesto — Smart Repair (`ui.py:445`)

```
pre_diag ──sana──> SKIPPED ⏭️ "network healthy, nothing to repair" (R4)
   │ rota
   ├─ flush-dns (si DNS failing)        → EXECUTED ⚠️
   ├─ renew-ip (si gateway_ok)          → EXECUTED/OK ⚠️ con details de lease
   ├─ _wait_for_settle(iface, ≤8s)      # poll: ip addr + nmcli GENERAL.STATE — no sleep ciego
   ├─ post_diag                          → delta real antes/después
   └─ veredicto:
       OK      → ✅ "SUCCESS (verified) — repairs 2/2, pre=FAIL post=OK"   (ui.py:505)
       PARTIAL → ⚠️ "DNS restored, WAN down → upstream/captive portal"     (ui.py:508)
       FAILED  → ❌ "repairs executed; NOT recovered → upstream/ISP + hints"
```

Flag `POST_REPAIR_VERIFY` (default ON). El diagnóstico inicial **no cuenta** en el ratio de repairs.

## 6. Pendientes conocidos (objetivo: llegar a cero)

| Ítem | Detalle | Acción |
|---|---|---|
| `change-dns` sin post-condición | Modifica perfil sin verificar resolución | Añadir `getent` recheck tras `nmcli con up` |
| `dhclient` fallback | Sin verificación + riesgo de conflicto con NM | Mantener tag `unverified-by-design`; nunca auto-escalar |
| STR-04/05 | `ufw`/`rfkill` parse por strings (output no localiza; riesgo bajo) | `sf-str: allow` con ratchet |
| Force renew real | `nmcli device reapply` **no** dispara DORA fresca; el path confiable documentado es `nmcli device disconnect/connect` — destructivo, solo como acción explícita | Backlog: acción "force renew" con advertencia |

> R1 (ICMP TCP-only) y R4 (short-circuit) ya aterrizaron conforme al doc — se tacha de pendientes en este mismo PR por regla §1.

## 7. Contrato del test guardián — `tests/test_verbs_doc.py`

```python
def test_every_catalog_verb_is_documented():
    # fuente de verdad: action_catalog.py + helper_verbs.py (registry)
    verbs = collect_registered_verbs()
    doc    = parse_verbs_md_tables()
    for v in verbs:
        assert v in doc, f"VERBO {v} sin fila en VERBS.md — regla §1"

def test_no_doc_drift():
    for row in parse_verbs_md_tables():
        assert row.verb in collect_registered_verbs()

def test_unverified_requires_tag():
    for row in parse_verbs_md_tables():
        if not row.post_condition:
            assert row.tag == "unverified-by-design" and row.justification

# Guardian 2 — lint anti-SF-STR (mismo archivo u otro):
def test_no_string_flow_control():
    # grepa el source por control de flujo sobre mensajes humanos:
    #   "in msg", "in message", "in stderr", '"..." in stdout.lower()'
    # allowlist: código de display puro (formateo de mensajes)
    ...
```

Un verbo nuevo sin fila, una fila huérfana, o un verbo sin post-condición y sin
justificación rompen el build. **El patrón SF-SEM no puede volver a crecer en silencio.**

## 8. Machine Registry — fuente parsable para guardian tests

> No parsear tablas markdown. Este bloque JSON es la fuente que `tests/test_verbs_doc.py` lee.
> Marcador anclado: el guardián exige `<!-- netmedic:verbs-registry v1 -->` antes del fence.

<!-- netmedic:verbs-registry v1 -->
```json
[
  {"verb": "flush-dns", "ipc_action": "flush_dns", "helper_verb": "flush-dns", "catalog": "privileged", "post_condition": "resolvectl flush-caches + service active check; standalone EXECUTED, verified via post_diag in Smart Repair", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "flush-dns", "file_line": "helper_verbs.py:122", "unverified": false},
  {"verb": "renew-ip", "ipc_action": "renew_ip", "helper_verb": "renew-ip", "catalog": "privileged", "post_condition": "ip -4 addr before/after + ping gw, details old_ip/new_ip/changed/gateway_ok", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "renew-ip", "file_line": "helper_verbs.py:128,134", "unverified": false},
  {"verb": "change-dns", "ipc_action": "change_dns", "helper_verb": "change-dns", "catalog": "privileged", "post_condition": "nmcli con mod + con up; unverified-by-design pending re-run network_status", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "change-dns", "file_line": "helper_verbs.py:145", "unverified": true, "justification": "modifica perfil NM; verificación natural re-run network_status"},
  {"verb": "restart-adapter", "ipc_action": "restart_adapter", "helper_verb": "restart-adapter", "catalog": "privileged", "post_condition": "ip -j link operstate UP poll 5s", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "restart-adapter", "file_line": "helper_verbs.py:166", "unverified": false},
  {"verb": "reset-stack", "ipc_action": "reset_tcp_ip_stack", "helper_verb": "reset-stack", "catalog": "privileged", "post_condition": "nmcli general status poll 15s", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "reset-stack", "file_line": "helper_verbs.py:177", "unverified": false},
  {"verb": "toggle-firewall", "ipc_action": "toggle_firewall", "helper_verb": "toggle-firewall", "catalog": "privileged", "post_condition": "get_firewall_status expected vs final", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "toggle-firewall", "file_line": "helper_verbs.py:184", "unverified": false},
  {"verb": "vpn-list", "ipc_action": "vpn_list_clients", "helper_verb": "vpn-list", "catalog": "privileged", "post_condition": "cat pki/index.txt parse", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "vpn-list", "file_line": "helper_verbs.py:192", "unverified": false},
  {"verb": "vpn-start-service", "ipc_action": "vpn_start_service", "helper_verb": "vpn-start-service", "catalog": "privileged", "post_condition": "is_service_active", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "vpn-start-service", "file_line": "helper_verbs.py:198", "unverified": false},
  {"verb": "vpn-restart-service", "ipc_action": "vpn_reconnect", "helper_verb": "vpn-restart-service", "catalog": "privileged", "post_condition": "is_service_active", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "vpn-restart-service", "file_line": "helper_verbs.py:198", "unverified": false},
  {"verb": "vpn-run-script", "ipc_action": "vpn_install", "helper_verb": "vpn-run-script", "catalog": "privileged", "post_condition": "SHA256 double + post-op check_status RUNNING + PKI index", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "vpn-run-script", "file_line": "helper_verbs.py:209", "unverified": false},
  {"verb": "vpn-run-script", "ipc_action": "vpn_create_client", "helper_verb": "vpn-run-script", "catalog": "privileged", "post_condition": "SHA256 double + PKI index verify", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "vpn-run-script", "file_line": "helper_verbs.py:209", "unverified": false},
  {"verb": "vpn-run-script", "ipc_action": "vpn_revoke_client", "helper_verb": "vpn-run-script", "catalog": "privileged", "post_condition": "SHA256 double + PKI index verify", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "vpn-run-script", "file_line": "helper_verbs.py:209", "unverified": false},
  {"verb": "iface-del", "ipc_action": null, "helper_verb": "iface-del", "catalog": "internal", "post_condition": "allowlist medic[0-9a-f]{6}", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "iface-del", "file_line": "helper_verbs.py:235", "unverified": false},
  {"verb": "iface-add-dummy", "ipc_action": null, "helper_verb": "iface-add-dummy", "catalog": "internal", "post_condition": "allowlist medic[0-9a-f]{6}", "file": "netmedic/netmedic/helper_verbs.py", "symbol": "iface-add-dummy", "file_line": "helper_verbs.py:239", "unverified": false},
  {"verb": "network_status", "ipc_action": "network_status", "helper_verb": null, "catalog": "safe", "post_condition": "probes multi-target DNS+TCP+https; ICMP details-only (not internet_ok); captive hint if gw_ok and not tcp_ok; NM connectivity divergence", "file": "netmedic/netmedic/probes.py", "symbol": "check_internet_access", "file_line": "probes.py:31", "unverified": false},
  {"verb": "wifi_diagnostics", "ipc_action": "wifi_diagnostics", "helper_verb": null, "catalog": "safe", "post_condition": "nmcli wifi scan parse", "file": "netmedic/netmedic/operators/wifi.py", "symbol": "scan_congestion", "file_line": "operators/wifi.py:382", "unverified": false},
  {"verb": "firewall_status", "ipc_action": "firewall_status", "helper_verb": null, "catalog": "safe", "post_condition": "ufw status parse", "file": "netmedic/netmedic/network.py", "symbol": "read_firewall_status", "file_line": "network.py:562", "unverified": false},
  {"verb": "vpn_status", "ipc_action": "vpn_status", "helper_verb": null, "catalog": "safe", "post_condition": "is_service_active", "file": "netmedic/netmedic/operators/vpn/angristan.py", "symbol": "check_status", "file_line": "angristan.py:360", "unverified": false},
  {"verb": "get_session_token", "ipc_action": "get_session_token", "helper_verb": null, "catalog": "safe", "post_condition": "IPC token issue", "file": "netmedic/netmedic/ipc_security.py", "symbol": "issue_token", "file_line": "ipc_security.py:49", "unverified": false},
  {"verb": "user_intent", "ipc_action": "user_intent", "helper_verb": null, "catalog": "safe", "post_condition": "AI guardrail validation", "file": "netmedic/netmedic/ipc_actions.py", "symbol": "_handle_user_intent", "file_line": "ipc_actions.py:341", "unverified": false},
  {"verb": "donate", "ipc_action": "donate", "helper_verb": null, "catalog": "safe", "post_condition": "open browser", "file": "netmedic/netmedic/ipc_actions.py", "symbol": "DONATE_URL", "file_line": "ipc_actions.py:254", "unverified": false}
]
```
