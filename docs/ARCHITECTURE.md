# Architecture Overview

## High-Level Design

```
┌─────────────────────────────────────────────────────────┐
│                     Entry Points                         │
│  python -m netmedic  │  python -m netmedic --headless    │
└────────────┬────────────────────────┬───────────────────┘
             │                        │
             ▼                        ▼
┌────────────────────┐    ┌──────────────────────┐
│   gui.py (GTK)     │    │   runtime.py loop    │
│   MainWindow       │    │   (no GTK import)    │
└────────┬───────────┘    └──────────┬───────────┘
         │                           │
         └───────────┬───────────────┘
                     ▼
         ┌───────────────────────┐
         │      runtime.py        │
         │  LifecycleManager      │
         │  NetMedicIPCServer     │
         │  IPCSession (tokens)   │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │    NetworkMedic        │
         │    (singleton)         │
         └───────────┬───────────┘
                     ▼
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
 CommandRunner   Operators        Config (XDG)
 (pkexec)        (WiFi, VPN)
```

## Core Modules

| Module | Responsibility |
|--------|---------------|
| `runtime.py` | Bootstrap, signals, IPC server, headless loop |
| `gui.py` | GTK entry helpers (`run_gui`, dialogs; `MainWindow` lives in `ui.py`) |
| `ui.py` / `ui_vpn.py` | Main window, Smart Repair sequence, VPN panel |
| `network.py` | Network diagnostics and repair operations |
| `probes.py` | Shared DNS/TCP/captive/NM probes (single source) |
| `sensors.py` | Read-only snapshot for AI/MCP |
| `system.py` | `CommandRunner` with log redaction, fixed-verb elevation |
| `models.py` | `ResultCode` (source of truth) + `NetResult`/`CommandResult` |
| `config.py` | XDG dirs, helper resolution, env gates |
| `action_catalog.py` | Single source of truth: action tiers + polkit IDs |
| `helper_verbs.py` / `helper_main.py` | Fixed-verb validation + privileged `netmedic-helper` CLI |
| `polkit_auth.py` | Polkit GI/`pkcheck` authorization, fail-closed skip |
| `audit_log.py` | Structured JSONL audit log with redaction |
| `status.py` | `netmedic --status/--status-json` health CLI |
| `lifecycle.py` | PID/lock/socket cleanup, stale lock recovery |
| `ipc_bridge.py` | Unix socket IPC server |
| `ipc_security.py` | Session tokens and peer identity for privileged IPC |
| `ipc_peer.py` | SO_PEERCRED UID/PID validation |
| `ipc_schema.py` | Versioned IPC action contract export |
| `ipc_actions.py` | Action dispatcher routing |
| `ipc_client.py` / `ipc_sync_client.py` | Async (GTK) / blocking IPC clients |
| `gui_actions.py` | GUI→IPC bridge |
| `operators/` | Pluggable infrastructure operators |

## Operator Pattern

All external system integrations implement `BaseOperator`:

```python
class BaseOperator(ABC):
    def check_status(self) -> NetResult: ...
    def install(self) -> NetResult: ...
    def stop(self) -> None: ...  # App-local cleanup only
```

VPN operator (`AngristanOperator`) pins script SHA256 before any execution.

## IPC Security Model (v1.6)

1. On startup, `IPCSession` issues a random token stored at `~/.local/state/netmedic/ipc.token` (mode 600, atomic create).
2. **All** actions require peer UID matching the daemon owner (`SO_PEERCRED`).
3. Safe actions need no confirmation/token/polkit; see [IPC_API.md](IPC_API.md).
4. Privileged actions require (order):
   - Peer UID match
   - `confirmed: true` (strict boolean)
   - Matching `session_token`
   - **Elevation:** `CommandRunner.run_elevated(verb)` → `pkexec /usr/libexec/netmedic/helper <verb>`  
     (IPC interactive polkit skipped when helper is active — single user prompt)
5. Action IDs / verbs / polkit IDs live in `action_catalog.py` + `helper_verbs.py`.
6. Privileged IPC attempts are recorded in `audit.log`.
7. **GUI → IPC bridge** (`gui_actions.GuiActionBridge`) for all catalog ops.

See [THREAT_MODEL.md](THREAT_MODEL.md) and [PRIVILEGED_HELPER.md](PRIVILEGED_HELPER.md).

## AI Pilot (Optional)

```
User (Ctrl+Space) → AIConsoleController → IPC (user_intent)
    → netmedic_ai.pilot.interpret_intent (GBNF-constrained LLM)
    → Preview dialog → User confirms → IPC (privileged action)
```

The `PilotoGuardrail` whitelists actions via `ActionRegistry` — only registered tool names can be proposed or executed.

## Lifecycle & Cleanup

On exit (normal or signal):
1. Stop IPC server
2. Remove state files (pid, sock, lock, token)
3. `NetworkMedic.cleanup()` — remove virtual test interfaces
4. `shutdown_operators()` — release operator resources (no system service stop)