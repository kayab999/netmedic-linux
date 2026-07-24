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

### Transport peer check

**Every** action requires peer UID matching the NetMedic process owner (`SO_PEERCRED`). Missing or foreign credentials fail closed with `requires_peer_auth`.

### Safe actions

No confirmation, token, or polkit required (peer UID still required):

- `network_status`, `wifi_diagnostics`, `firewall_status`
- `vpn_status`
- `get_session_token` (same-owner peer only)
- `user_intent`, `donate`

### Privileged actions

Require **all** of (checked in this order — cheap checks first):

1. Peer UID matching the NetMedic process owner
2. `confirmed: true` (strict boolean — not `"true"` or `1`)
3. Valid `session_token` from `get_session_token` (**before** polkit, to avoid prompt spam)
4. PolicyKit authorization for the mapped action ID

Privileged actions: `flush_dns`, `renew_ip`, `change_dns`, `restart_adapter`, `reset_tcp_ip_stack`, `toggle_firewall`, `vpn_reconnect`, `vpn_create_client`, `vpn_revoke_client`, `vpn_list_clients`, `vpn_install`, `vpn_start_service`.

Note: `vpn_list_clients` is privileged because it elevates to read the EasyRSA PKI index. `vpn_install` / `vpn_start_service` elevate installer and systemd unit control.

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
6. Install the system polkit policy once:
   `./scripts/install-polkit-policy.sh`
   (or `sudo cp assets/com.kayab.netmedic.policy /usr/share/polkit-1/actions/`).

## GUI bridge

The desktop UI uses `netmedic.gui_actions.GuiActionBridge` (SyncIPCClient) for
repair, infrastructure, and all VPN catalog actions (including install/start) so
GUI clicks share the same token/polkit/audit path as MCP and AI. Residual local
elevation: virtual-interface cleanup on exit only.

See [THREAT_MODEL.md](THREAT_MODEL.md) for trust boundaries and residual risks.