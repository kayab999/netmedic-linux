import signal
from unittest.mock import MagicMock, patch

from netmedic.network import NetworkMedic
from netmedic.runtime import handle_signals


def test_network_medic_singleton():
    medic1 = NetworkMedic()
    medic2 = NetworkMedic()
    assert medic1 is medic2


@patch("netmedic.system.CommandRunner.run")
def test_cleanup_on_signal(mock_run):
    mock_run.return_value = MagicMock(success=True)

    medic = NetworkMedic()
    with medic._state_lock:
        medic._created_ifaces.add("medic99")

    assert "medic99" in medic._created_ifaces

    res = medic.cleanup()

    assert res.success is True
    assert "medic99" not in medic._created_ifaces
    mock_run.assert_called_with(["ip", "link", "del", "medic99"], require_root=True)


def test_signal_handler_registration():
    original_int = signal.signal(signal.SIGINT, handle_signals)
    original_term = signal.signal(signal.SIGTERM, handle_signals)

    assert signal.getsignal(signal.SIGINT) is handle_signals
    assert signal.getsignal(signal.SIGTERM) is handle_signals

    signal.signal(signal.SIGINT, original_int)
    signal.signal(signal.SIGTERM, original_term)