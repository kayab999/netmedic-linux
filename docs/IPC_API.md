# NetMedic IPC API v1.0

NetMedic exposes a local Unix socket API for automation, MCP, AI, and third-party clients. The GUI is one client; the IPC core is the platform contract.

## Transport

| Property | Value |
|----------|-------|
| Socket | `~/.local/state/netmedic/ipc.sock` (mode `600`) |
| Framing | Newline-delimited JSON (max 64 KiB per message) |
| Timeout | 30 seconds per request |
| Peer identity | `SO_PEERCRED` — peer UID must match the daemon owner |

## Request format

```json
{"action": "network_status", "params": {}}
```

## Response format

```json
{"status": "ok", "success": true, "message": "...", "operation": "..."}
```

Errors include `"status": "error"` and a `"message"`. Privileged denials may add `requires_confirmation`, `requires_polkit`, or `requires_peer_auth`.

## Authorization tiers

### Safe actions

No confirmation, token, or polkit required:

- `network_status`, `wifi_diagnostics`, `firewall_status`
- `vpn_status`, `vpn_list_clients`
- `get_session_token` (same-owner peer only)
- `user_intent`, `donate`

### Privileged actions

Require **all** of:

1. `confirmed: true` (strict boolean — not `"true"` or `1`)
2. Valid `session_token` from `get_session_token`
3. PolicyKit authorization for the mapped action ID
4. Peer UID matching the NetMedic process owner

Privileged actions: `flush_dns`, `renew_ip`, `change_dns`, `restart_adapter`, `reset_tcp_ip_stack`, `toggle_firewall`, `vpn_reconnect`, `vpn_create_client`, `vpn_revoke_client`.

Policy definitions: `assets/com.kayab.netmedic.policy`.

## Machine-readable schema

```python
from netmedic.ipc_schema import export_schema
print(export_schema())
```

## Python client

```python
from netmedic.ipc_sync_client import SyncIPCClient

client = SyncIPCClient()
if not client.is_available():
    raise SystemExit("Start NetMedic first: netmedic --headless")

status = client.request("network_status")
print(status)

result = client.request("flush_dns", confirmed=True)
print(result)
```

`SyncIPCClient` obtains the session token automatically for privileged calls.

## Headless daemon

```bash
netmedic --headless
```

Or install the systemd user unit via `./install.sh` and enable:

```bash
systemctl --user enable --now netmedic-headless.service
```

## Audit evidence

Privileged attempts (granted and denied) append JSON lines to `~/.local/state/netmedic/audit.log` (mode `600`). Session tokens are never written to the audit log.

## Integration checklist

1. Ensure NetMedic daemon is running (GUI or `--headless`).
2. Connect to the Unix socket in the user's state directory.
3. Call `get_session_token` before privileged operations.
4. Pass `confirmed: true` and `session_token` for privileged actions.
5. Handle polkit prompts (GUI agent or `pkttyagent` for headless mutation).

See [THREAT_MODEL.md](THREAT_MODEL.md) for trust boundaries and residual risks.