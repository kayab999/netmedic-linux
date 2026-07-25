"""Phase D: IPC skips interactive polkit when helper elevation is active."""

import os
from unittest.mock import MagicMock, patch

from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_security import IPCSession
from netmedic.models import NetResult

_PEER = {"peer_uid": os.getuid(), "peer_pid": os.getpid()}


def test_helper_mode_skips_ipc_polkit(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")
    # Do not allow legacy; elevation mocked at run_elevated.
    monkeypatch.setenv("NETMEDIC_ALLOW_LEGACY_ELEVATION", "0")

    session = IPCSession()
    token = session.issue_token()
    medic = MagicMock()
    medic.flush_dns.return_value = NetResult("Flush DNS", True, "flushed")

    with patch("netmedic.ipc_security.check_authorization") as mock_polkit:
        with patch(
            "netmedic.system.CommandRunner.run_elevated",
            return_value=MagicMock(success=True, stdout="", stderr=""),
        ):
            # NetworkMedic.flush_dns calls run_elevated; patch at network layer too.
            with patch(
                "netmedic.network.CommandRunner.run_elevated",
                return_value=MagicMock(success=True, stdout="", stderr=""),
            ):
                with patch(
                    "netmedic.network.CommandRunner.is_service_active",
                    return_value=True,
                ):
                    dispatch = create_action_dispatcher(medic, session)
                    # Use real NetworkMedic path via dispatcher — medic is mock so
                    # flush_dns on mock is fine if dispatcher uses medic instance.
                    medic.flush_dns.return_value = NetResult(
                        "Flush DNS", True, "systemd-resolved cache flushed"
                    )
                    result = dispatch(
                        "flush_dns",
                        {"confirmed": True, "session_token": token},
                        **_PEER,
                    )

    assert result["status"] == "ok"
    mock_polkit.assert_not_called()
