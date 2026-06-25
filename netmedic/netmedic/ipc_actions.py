import logging
from typing import Any, Callable, Dict

from netmedic.network import NetworkMedic
from netmedic.operators.wifi import WifiOperator
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.ipc_security import IPCSession

DONATE_URL = "https://buymeacoffee.com/kayabsoftware"

logger = logging.getLogger(__name__)


def _result_payload(result) -> Dict[str, Any]:
    return {
        "status": "ok" if result.success else "error",
        "success": result.success,
        "message": result.message,
        "operation": result.operation,
    }


def create_action_dispatcher(
    medic: NetworkMedic,
    session: IPCSession,
) -> Callable[[str, Dict[str, Any]], Dict[str, Any]]:
    """Builds the IPC action router bound to a NetworkMedic instance."""
    wifi = WifiOperator()
    vpn = AngristanOperator()

    def dispatch(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if action == "get_session_token":
                token = session.get_token()
                return {"status": "ok", "session_token": token}

            auth_error = session.validate_privileged(action, params)
            if auth_error:
                return auth_error

            if action == "user_intent":
                return _handle_user_intent(params)

            if action == "network_status":
                return _result_payload(medic.run_diagnostics())

            if action == "wifi_diagnostics":
                return _result_payload(wifi.scan_congestion())

            if action == "flush_dns":
                return _result_payload(medic.flush_dns())

            if action == "renew_ip":
                return _result_payload(medic.renew_ip())

            if action == "vpn_reconnect":
                return _result_payload(vpn.restart_service())

            if action == "donate":
                return {"status": "ok", "message": "Opening donation page.", "url": DONATE_URL}

            if action == "change_dns":
                server = params.get("server", "1.1.1.1")
                return _result_payload(medic.change_dns(server))

            if action == "restart_adapter":
                return _result_payload(medic.restart_adapter())

            if action == "reset_tcp_ip_stack":
                return _result_payload(medic.reset_tcp_ip_stack())

            if action == "toggle_firewall":
                return _result_payload(medic.toggle_firewall())

            return {"status": "error", "message": f"Acción desconocida: {action}"}
        except Exception as exc:
            logger.exception("IPC dispatch failed for action=%s", action)
            return {"status": "error", "message": str(exc)}

    return dispatch


def _handle_user_intent(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delegates natural-language requests to the AI pilot when available."""
    try:
        from netmedic_ai.pilot import interpret_intent  # type: ignore[import-untyped]
    except ImportError:
        return {
            "status": "error",
            "message": "Módulo AI no disponible. Instale con: pip install .[ai]",
        }

    user_request = params.get("user_request", "")
    network_state = params.get("network_state", {})
    if not user_request:
        return {"status": "error", "message": "Solicitud vacía."}

    try:
        return interpret_intent(user_request, network_state)
    except Exception as exc:
        logger.exception("AI intent interpretation failed")
        return {"status": "error", "message": str(exc)}