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
| `gui.py` | GTK initialization and main window |
| `network.py` | Network diagnostics and repair operations |
| `system.py` | `CommandRunner` with log redaction |
| `lifecycle.py` | PID/lock/socket cleanup, stale lock recovery |
| `ipc_bridge.py` | Unix socket IPC server |
| `ipc_security.py` | Session tokens and peer identity for privileged IPC |
| `ipc_peer.py` | SO_PEERCRED UID/PID validation |
| `ipc_schema.py` | Versioned IPC action contract export |
| `ipc_actions.py` | Action dispatcher routing |
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

## IPC Security Model (v1.4)

1. On startup, `IPCSession` issues a random token stored at `~/.local/state/netmedic/ipc.token` (mode 600).
2. Safe actions execute without confirmation; see [IPC_API.md](IPC_API.md) for the full contract.
3. Privileged actions require:
   - Peer UID matching the daemon owner (`ipc_peer.py`)
   - `confirmed: true` (strict boolean)
   - Polkit authorization for the mapped action ID
   - Matching `session_token` in params
4. Action IDs and classifications live in `action_catalog.py`; exported schema in `ipc_schema.py`.
5. Privileged attempts are recorded in `audit.log`; polkit prompts are triggered server-side.

See [THREAT_MODEL.md](THREAT_MODEL.md) for actor and residual-risk analysis.

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