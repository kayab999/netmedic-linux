from unittest.mock import MagicMock, patch

from netmedic.integration import shutdown_operators
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.operators.vpn.base import VPNClient


def test_revoke_client_verification():
    op = AngristanOperator()

    with patch.object(
        op,
        "_execute_verified_script",
        return_value=MagicMock(success=True, stdout="", stderr=""),
    ):
        with patch.object(op, "list_clients") as mock_list:
            mock_list.return_value = MagicMock(
                success=True,
                data=[VPNClient(name="revoked-client", active=False)],
            )
            result = op.revoke_client("revoked-client")

    assert result.success is True
    assert "verified" in result.message.lower()


@patch("netmedic.system.CommandRunner.run")
def test_angristan_stop_does_not_stop_service(mock_run):
    op = AngristanOperator()
    op.stop()
    mock_run.assert_not_called()


def test_shutdown_operators_calls_stop():
    op_a = MagicMock()
    op_a.name = "Operator A"
    op_b = MagicMock()
    op_b.name = "Operator B"

    shutdown_operators([op_a, op_b])

    op_a.stop.assert_called_once()
    op_b.stop.assert_called_once()