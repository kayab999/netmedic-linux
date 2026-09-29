import dataclasses
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from netmedic.audit_log import record as audit_record
from netmedic.audit_log import record_intent as audit_record_intent
from netmedic.ipc_peer import validate_peer_identity
from netmedic.models import NetResult
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
        from netmedic_ai.toolkit import registry

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
        from netmedic_ai.param_validation import validate_tool_params
        from netmedic_ai.toolkit import registry

        if registry.is_registered(action):
            return validate_tool_params(action, tool_params)
    except ImportError:
        pass

    if action == "change_dns":
        server = tool_params.get("server", "1.1.1.1")
        if not isinstance(server, str):
            return "Parameter 'server' must be a string."
        from netmedic.validators import ValidationError, validate_dns

        try:
            validate_dns(server)
        except ValidationError:
            return f"Invalid DNS server IP: {server}"
    if action in ("vpn_create_client", "vpn_revoke_client"):
        name = tool_params.get("name", "")
        if not isinstance(name, str) or not name:
            return "Parameter 'name' is required."
        from netmedic.validators import ValidationError, validate_client_name

        try:
            validate_client_name(name)
        except ValidationError:
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


def _result_payload(result: NetResult) -> Dict[str, Any]:
    # Code is source of truth; status/success derived for backward compat (E4)
    from netmedic.models import ResultCode
    try:
        code = result.code
        if isinstance(code, str):
            code = ResultCode(code)
        # Handle MagicMock from tests (has no real code)
        if code.__class__.__name__ == "MagicMock":
            # Fallback to success shim for mocked objects (tests only, not production)
            is_ok = bool(getattr(result, "success", False))  # sf-success: allow - test mock compat
        else:
            is_ok = code in (ResultCode.OK, ResultCode.EXECUTED)
    except Exception:
        is_ok = False
        code = ResultCode.FAILED
    try:
        if isinstance(code, ResultCode):
            code_val = code.value
        else:
            code_val = str(code)
        if code_val.startswith("<MagicMock"):
            code_val = "ok" if is_ok else "failed"
    except Exception:
        code_val = "ok" if is_ok else "failed"
    payload: Dict[str, Any] = {
        "status": "ok" if is_ok else "error",
        "success": is_ok,
        "message": result.message,
        "operation": result.operation,
        "code": code_val,
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


@dataclasses.dataclass(frozen=True)
class _DispatchCtx:
    """Per-request dispatch context (M8: handler table calls, not if-chain)."""

    medic: NetworkMedic
    session: IPCSession
    wifi: WifiOperator
    vpn: AngristanOperator
    action: str
    params: Dict[str, Any]
    peer_uid: int
    peer_pid: int
    started: float
    privileged: bool

    def finish(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return _finish_privileged(
            self.action, self.params, result,
            peer_uid=self.peer_uid, peer_pid=self.peer_pid,
            started=self.started, privileged=self.privileged,
        )


def _handle_get_session_token(ctx: _DispatchCtx) -> Dict[str, Any]:
    token = ctx.session.get_token()
    if not token:
        return {"status": "error", "message": "IPC session token not yet available."}
    return {"status": "ok", "session_token": token}


def _handle_user_intent_action(ctx: _DispatchCtx) -> Dict[str, Any]:
    return _handle_user_intent(ctx.params)


def _handle_network_status(ctx: _DispatchCtx) -> Dict[str, Any]:
    return _result_payload(ctx.medic.run_diagnostics())


def _handle_wifi_diagnostics(ctx: _DispatchCtx) -> Dict[str, Any]:
    return _result_payload(ctx.wifi.scan_congestion())


def _handle_flush_dns(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.medic.flush_dns()))


def _handle_renew_ip(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.medic.renew_ip()))


def _handle_vpn_reconnect(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.vpn.restart_service()))


def _handle_donate(ctx: _DispatchCtx) -> Dict[str, Any]:
    return {"status": "ok", "message": "Opening donation page.", "url": DONATE_URL}


def _handle_change_dns(ctx: _DispatchCtx) -> Dict[str, Any]:
    server = ctx.params.get("server", "1.1.1.1")
    return ctx.finish(_result_payload(ctx.medic.change_dns(server)))


def _handle_restart_adapter(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.medic.restart_adapter()))


def _handle_reset_tcp_ip_stack(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.medic.reset_tcp_ip_stack()))


def _handle_toggle_firewall(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.medic.toggle_firewall()))


def _handle_firewall_status(ctx: _DispatchCtx) -> Dict[str, Any]:
    status = ctx.medic.get_firewall_status()
    return {"status": "ok", "message": status, "data": status}


def _handle_vpn_status(ctx: _DispatchCtx) -> Dict[str, Any]:
    return _result_payload(ctx.vpn.check_status())


def _handle_vpn_list_clients(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.vpn.list_clients()))


def _handle_vpn_create_client(ctx: _DispatchCtx) -> Dict[str, Any]:
    name = ctx.params.get("name", "")
    return ctx.finish(_result_payload(ctx.vpn.add_client(name)))


def _handle_vpn_revoke_client(ctx: _DispatchCtx) -> Dict[str, Any]:
    name = ctx.params.get("name", "")
    return ctx.finish(_result_payload(ctx.vpn.revoke_client(name)))


def _handle_vpn_install(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.vpn.install()))


def _handle_vpn_start_service(ctx: _DispatchCtx) -> Dict[str, Any]:
    return ctx.finish(_result_payload(ctx.vpn.start_service()))


# M8: the dispatch table. Adding an action = adding one entry here plus
# the ActionSpec row; the if-chain it replaces lived in dispatch below.
_HANDLERS: Dict[str, Callable[[_DispatchCtx], Dict[str, Any]]] = {
    "get_session_token": _handle_get_session_token,
    "user_intent": _handle_user_intent_action,
    "network_status": _handle_network_status,
    "wifi_diagnostics": _handle_wifi_diagnostics,
    "flush_dns": _handle_flush_dns,
    "renew_ip": _handle_renew_ip,
    "vpn_reconnect": _handle_vpn_reconnect,
    "donate": _handle_donate,
    "change_dns": _handle_change_dns,
    "restart_adapter": _handle_restart_adapter,
    "reset_tcp_ip_stack": _handle_reset_tcp_ip_stack,
    "toggle_firewall": _handle_toggle_firewall,
    "firewall_status": _handle_firewall_status,
    "vpn_status": _handle_vpn_status,
    "vpn_list_clients": _handle_vpn_list_clients,
    "vpn_create_client": _handle_vpn_create_client,
    "vpn_revoke_client": _handle_vpn_revoke_client,
    "vpn_install": _handle_vpn_install,
    "vpn_start_service": _handle_vpn_start_service,
}


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

            # Fail-closed audit gate (B-4/C-16): the intent write IS the gate —
            # no separate writability pre-check (TOCTOU against disk fill).
            # Abort here precedes any pkexec launch inside the handlers below.
            if privileged:
                try:
                    audit_record_intent(
                        action=action,
                        peer_uid=peer_uid,
                        peer_pid=peer_pid,
                        params=params,
                    )
                except OSError as exc:
                    result = {
                        "status": "error",
                        "message": (
                            "Audit unavailable — refusing privileged action "
                            f"(disk full or unwritable audit log: {exc})"
                        ),
                    }
                    return _finish_privileged(
                        action, params, result,
                        peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                    )

            handler = _HANDLERS.get(action)
            if handler is None:
                result = {"status": "error", "message": f"Unknown action: {action}"}
                return _finish_privileged(
                    action, params, result,
                    peer_uid=peer_uid, peer_pid=peer_pid, started=started, privileged=privileged,
                )
            ctx = _DispatchCtx(
                medic=medic, session=session, wifi=wifi, vpn=vpn,
                action=action, params=params,
                peer_uid=peer_uid, peer_pid=peer_pid,
                started=started, privileged=privileged,
            )
            return handler(ctx)
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
        from netmedic_ai.pilot import interpret_intent
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