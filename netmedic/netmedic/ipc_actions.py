import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from netmedic.audit_log import record as audit_record
from netmedic.ipc_peer import validate_peer_identity
from netmedic.network import NetworkMedic
from netmedic.operators.wifi import WifiOperator
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.action_catalog import PRIVILEGED_ACTIONS, SAFE_ACTIONS, is_internal, is_privileged
from netmedic.ipc_security import IPCSession

DONATE_URL = "https://buymeacoffee.com/kayabsoftware"

# Serialize privileged execution so concurrent pkexec/polkit work cannot exhaust
# the IPC worker pool (documented residual risk in THREAT_MODEL).
_MAX_CONCURRENT_PRIVILEGED = 1
_privileged_slots = threading.Semaphore(_MAX_CONCURRENT_PRIVILEGED)

logger = logging.getLogger(__name__)

def _validate_action(action: str) -> Optional[Dict[str, Any]]:
    if is_internal(action):
        return None
    try:
        from netmedic_ai.toolkit import registry  # type: ignore[import-untyped]

        if registry.is_registered(action):
            return None
    except ImportError:
        pass
    if action in SAFE_ACTIONS or action in PRIVILEGED_ACTIONS:
        return None
    return {"status": "error", "message": f"Unknown action: {action}"}


def _validate_dispatch_params(action: str, params: Dict[str, Any]) -> Optional[str]:
    """Server-side param checks shared by IPC (AI package optional)."""
    # Strip auth-only keys before tool-specific validation.
    tool_params = {
        k: v
        for k, v in params.items()
        if k not in ("confirmed", "session_token")
    }

    try:
        from netmedic_ai.param_validation import validate_tool_params  # type: ignore[import-untyped]
        from netmedic_ai.toolkit import registry  # type: ignore[import-untyped]

        if registry.is_registered(action):
            return validate_tool_params(action, tool_params)
    except ImportError:
        pass

    if action == "change_dns":
        server = tool_params.get("server", "1.1.1.1")
        if not isinstance(server, str):
            return "Parameter 'server' must be a string."
        import re

        if not re.fullmatch(
            r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)",
            server,
        ):
            return f"Invalid DNS server IP: {server}"
    if action in ("vpn_create_client", "vpn_revoke_client"):
        name = tool_params.get("name", "")
        if not isinstance(name, str) or not name:
            return "Parameter 'name' is required."
        import re

        if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
            return "Invalid client name (use a-z, 0-9, -, _)"
    if action == "user_intent":
        req = tool_params.get("user_request", "")
        if not isinstance(req, str) or not req.strip():
            return "Empty request."
    return None


def _audit_dispatch(
    action: str,
    params: Dict[str, Any],
    result: Dict[str, Any],
    *,
    peer_uid: int,
    peer_pid: int,
    started: float,
) -> None:
    outcome = "ok" if result.get("status") == "ok" else "error"
    audit_record(
        action=action,
        peer_uid=peer_uid,
        peer_pid=peer_pid,
        params=params,
        result=result,
        duration_ms=(time.monotonic() - started) * 1000,
        outcome=outcome,
    )


def _finish_privileged(
    action: str,
    params: Dict[str, Any],
    result: Dict[str, Any],
    *,
    peer_uid: int,
    peer_pid: int,
    started: float,
    privileged: bool,
) -> Dict[str, Any]:
    if privileged:
        _audit_dispatch(
            action, params, result, peer_uid=peer_uid, peer_pid=peer_pid, started=started
        )
    return result


def _result_payload(result) -> Dict[str, Any]:
    payload = {
        "status": "ok" if result.success else "error",
        "success": result.success,
        "message": result.message,
        "operation": result.operation,
    }
    if result.details is not None:
        payload["details"] = result.details
    if result.data is not None:
        if isinstance(result.data, list):
            payload["data"] = [
                {"name": c.name, "active": c.active} if hasattr(c, "name") else c
                for c in result.data
            ]
        else:
            payload["data"] = result.data
    return payload


def create_action_dispatcher(
    medic: NetworkMedic,
    session: IPCSession,
) -> Callable[..., Dict[str, Any]]:
    """Builds the IPC action router bound to a NetworkMedic instance."""
    wifi = WifiOperator()
    vpn = AngristanOperator()

    def dispatch(
        action: str,
        params: Dict[str, Any],
        *,
        peer_uid: int = -1,
        peer_pid: int = -1,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        privileged = False
        held_privileged_slot = False
        try:
            if not isinstance(action, str) or not action:
                return {"status": "error", "message": "Invalid request shape: action must be a non-empty string."}
            if not isinstance(params, dict):
                return {"status": "error", "message": "Invalid request shape: params must be an object."}

            # Defense in depth: peer UID on every action (docs claim transport peer check).
            peer_error = validate_peer_identity(peer_uid, peer_pid)
            if peer_error:
                return peer_error

            if action == "get_session_token":
                token = session.get_token()
                if not token:
                    return {"status": "error", "message": "IPC session token not yet available."}
                return {"status": "ok", "session_token": token}

            unknown = _validate_action(action)
            if unknown:
                return unknown

            privileged = is_privileged(action)

            auth_error = session.validate_privileged(
                action, params, peer_uid=peer_uid, peer_pid=peer_pid
            )
            if auth_error:
                if privileged:
                    audit_record(
                        action=action,
                        peer_uid=peer_uid,
                        peer_pid=peer_pid,
                        params=params,
                        result=auth_error,
                        duration_ms=(time.monotonic() - started) * 1000,
                        outcome="denied",
                    )
                return auth_error

            param_err = _validate_dispatch_params(action, params)
            if param_err:
                result = {"status": "error", "message": param_err}
                return _finish_privileged(
                    action, params, result,
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if privileged:
                if not _privileged_slots.acquire(blocking=False):
                    busy = {
                        "status": "error",
                        "message": (
                            "Another privileged operation is already running. "
                            "Retry after it completes."
                        ),
                        "busy": True,
                    }
                    audit_record(
                        action=action,
                        peer_uid=peer_uid,
                        peer_pid=peer_pid,
                        params=params,
                        result=busy,
                        duration_ms=(time.monotonic() - started) * 1000,
                        outcome="denied",
                    )
                    return busy
                held_privileged_slot = True

            if action == "user_intent":
                return _handle_user_intent(params)

            if action == "network_status":
                return _result_payload(medic.run_diagnostics())

            if action == "wifi_diagnostics":
                return _result_payload(wifi.scan_congestion())

            if action == "flush_dns":
                return _finish_privileged(
                    action, params, _result_payload(medic.flush_dns()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "renew_ip":
                return _finish_privileged(
                    action, params, _result_payload(medic.renew_ip()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "vpn_reconnect":
                return _finish_privileged(
                    action, params, _result_payload(vpn.restart_service()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "donate":
                return {"status": "ok", "message": "Opening donation page.", "url": DONATE_URL}

            if action == "change_dns":
                server = params.get("server", "1.1.1.1")
                return _finish_privileged(
                    action, params, _result_payload(medic.change_dns(server)),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "restart_adapter":
                return _finish_privileged(
                    action, params, _result_payload(medic.restart_adapter()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "reset_tcp_ip_stack":
                return _finish_privileged(
                    action, params, _result_payload(medic.reset_tcp_ip_stack()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "toggle_firewall":
                return _finish_privileged(
                    action, params, _result_payload(medic.toggle_firewall()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "firewall_status":
                status = medic.get_firewall_status()
                return {"status": "ok", "message": status, "data": status}

            if action == "vpn_status":
                return _result_payload(vpn.check_status())

            if action == "vpn_list_clients":
                return _finish_privileged(
                    action, params, _result_payload(vpn.list_clients()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "vpn_create_client":
                name = params.get("name", "")
                return _finish_privileged(
                    action, params, _result_payload(vpn.add_client(name)),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "vpn_revoke_client":
                name = params.get("name", "")
                return _finish_privileged(
                    action, params, _result_payload(vpn.revoke_client(name)),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "vpn_install":
                return _finish_privileged(
                    action, params, _result_payload(vpn.install()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            if action == "vpn_start_service":
                return _finish_privileged(
                    action, params, _result_payload(vpn.start_service()),
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )

            result = {"status": "error", "message": f"Unknown action: {action}"}
            return _finish_privileged(
                action, params, result,
                peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
            )
        except Exception:
            logger.exception("IPC dispatch failed for action=%s", action)
            result = {"status": "error", "message": "Internal IPC error."}
            if privileged or is_privileged(action):
                _audit_dispatch(
                    action, params, result, peer_uid=peer_uid, peer_pid=peer_pid, started=started
                )
            return result
        finally:
            if held_privileged_slot:
                _privileged_slots.release()

    return dispatch


def _handle_user_intent(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delegates natural-language requests to the AI pilot when available."""
    try:
        from netmedic_ai.pilot import interpret_intent  # type: ignore[import-untyped]
    except ImportError:
        return {
            "status": "error",
            "message": "AI module not available. Install with: pip install -e 'netmedic[ai]'",
        }

    user_request = params.get("user_request", "")
    network_state = params.get("network_state", {})
    if not user_request:
        return {"status": "error", "message": "Empty request."}

    try:
        return interpret_intent(user_request, network_state)
    except Exception as exc:
        logger.exception("AI intent interpretation failed")
        return {"status": "error", "message": str(exc)}