"""Peer identity checks for Unix socket IPC clients."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional


def validate_peer_identity(peer_uid: int, peer_pid: int) -> Optional[Dict[str, Any]]:
    """Return an error payload when peer credentials are missing or untrusted."""
    if peer_uid < 0 or peer_pid < 0:
        return {
            "status": "error",
            "message": "Missing peer credentials.",
            "requires_peer_auth": True,
        }
    if peer_uid != os.getuid():
        return {
            "status": "error",
            "message": "IPC peer UID does not match the NetMedic process owner.",
            "requires_peer_auth": True,
        }
    return None