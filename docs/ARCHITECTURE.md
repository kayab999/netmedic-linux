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
| `ipc_security.py` | Session tokens for privileged IPC actions |
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

## IPC Security Model

1. On startup, `IPCSession` issues a random token stored at `~/.local/state/netmedic/ipc.token` (mode 600).
2. Read-only actions (`network_status`, `user_intent`, `wifi_diagnostics`) execute without confirmation.
3. Privileged actions require `confirmed: true` and matching `session_token` in params.
4. The AI console passes both after user authorization in the preview dialog.

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