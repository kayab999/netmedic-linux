import pytest

from netmedic.ipc_client import PilotClient


@pytest.fixture(autouse=True)
def _reset_ipc_client_singleton():
    """Isolate IPC client state between tests."""
    PilotClient.reset_singleton()
    yield
    PilotClient.reset_singleton()