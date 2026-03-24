# ✅ NetMedic Release Checklist

Use this checklist to validate a release candidate before public distribution.

## 1. Installation & Environment
- [ ] **Clean Install**: Run `sudo ./install_system.sh` on a clean VM/Environment.
    - [ ] Verify `/opt/netmedic` exists.
    - [ ] Verify `/usr/bin/netmedic` exists and is executable.
    - [ ] Verify icon appears in System Menu.
- [ ] **Startup**: Launch `netmedic` from terminal.
    - [ ] Verify no immediate crash.
    - [ ] Verify logs created in `~/.local/state/netmedic/netmedic.log`.
    - [ ] Verify permissions of log file are `600` (User Read/Write only).

## 2. Basic Repair (Safe Actions)
- [ ] **Diagnostics**: Run Check Connectivity.
    - [ ] Verify output in log area.
    - [ ] Verify Spinner activity.
- [ ] **Flush DNS**: Run action.
    - [ ] Verify success message.
- [ ] **Renew IP**: Run action.
    - [ ] Verify prompt for password (pkexec).
    - [ ] Verify network reconnection.

## 3. Infrastructure (Advanced)
- [ ] **VPN Operator**:
    - [ ] **Status**: Should show "Not Installed" initially.
    - [ ] **Install**: Click "Install OpenVPN".
        - [ ] Verify confirmation dialog.
        - [ ] Verify installer download (check `~/.local/share/netmedic/operators/`).
        - [ ] Verify terminal/log output during install.
        - [ ] **Success**: Status changes to "Running".
    - [ ] **Add Client**:
        - [ ] Add client "test-user".
        - [ ] Verify client appears in list with "Active" status.
    - [ ] **Revoke Client**:
        - [ ] Revoke "test-user".
        - [ ] Verify confirmation dialog.
        - [ ] Verify status changes to "Revoked" or removed from list.
- [ ] **System Tools**:
    - [ ] **Firewall**: Toggle UFW. Verify system notification or log reflection.

## 4. Resilience & Safety
- [ ] **Cancellation**: Click "Reset TCP/IP", then Cancel the dialog.
    - [ ] Verify NO action was taken.
- [ ] **Auth Failure**: Click a root action, then Cancel the OS password prompt.
    - [ ] Verify app handles it gracefully (Log: "Authentication cancelled").
- [ ] **Log Rotation**: (Optional) Check that logs rotate if size limit reached.
