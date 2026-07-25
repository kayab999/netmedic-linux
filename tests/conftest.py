import pytest

from netmedic.ipc_client import PilotClient


@pytest.fixture(autouse=True)
def _reset_ipc_client_singleton():
    """Isolate IPC client state between tests."""
    PilotClient.reset_singleton()
    yield
    PilotClient.reset_singleton()


@pytest.fixture(autouse=True)
def _skip_polkit_in_tests(monkeypatch):
    """Tests mock polkit explicitly; default to skip for direct dispatch calls."""
    monkeypatch.setenv("NETMEDIC_TEST_MODE", "1")
    monkeypatch.setenv("NETMEDIC_SKIP_POLKIT", "1")
    # Host may have /usr/libexec/netmedic/helper installed (auto-on). Force
    # legacy elevation unless a test explicitly opts into helper mode.
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")