import signal
from unittest.mock import MagicMock, patch

from netmedic.network import NetworkMedic
from netmedic.runtime import handle_signals


def test_network_medic_singleton():
    medic1 = NetworkMedic()
    medic2 = NetworkMedic()
    assert medic1 is medic2


@patch("netmedic.system.CommandRunner.run_elevated")
def test_cleanup_on_signal(mock_elevated):
    mock_elevated.return_value = MagicMock(success=True)

    medic = NetworkMedic()
    with medic._state_lock:
        medic._created_ifaces.add("medicabcdef")

    assert "medicabcdef" in medic._created_ifaces

    res = medic.cleanup()

    assert res.success is True
    assert "medicabcdef" not in medic._created_ifaces
    mock_elevated.assert_called_with("iface-del", {"iface": "medicabcdef"})


def test_signal_handler_registration():
    original_int = signal.signal(signal.SIGINT, handle_signals)
    original_term = signal.signal(signal.SIGTERM, handle_signals)

    assert signal.getsignal(signal.SIGINT) is handle_signals
    assert signal.getsignal(signal.SIGTERM) is handle_signals

    signal.signal(signal.SIGINT, original_int)
    signal.signal(signal.SIGTERM, original_term)