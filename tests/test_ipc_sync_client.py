from unittest.mock import patch

from netmedic.ipc_sync_client import SyncIPCClient


@patch("netmedic.ipc_sync_client.os.path.exists", return_value=False)
def test_request_requires_running_instance(mock_exists):
    client = SyncIPCClient(sock_path="/tmp/missing.sock")
    result = client.request("network_status")
    assert result["status"] == "error"
    assert "not available" in result["message"]


@patch("netmedic.ipc_sync_client.SyncIPCClient._raw_request")
@patch("netmedic.ipc_sync_client.os.path.exists", return_value=True)
def test_privileged_request_attaches_token(mock_exists, mock_raw):
    mock_raw.side_effect = [
        {"status": "ok", "session_token": "abc"},
        {"status": "ok", "message": "done"},
    ]
    client = SyncIPCClient(sock_path="/tmp/ipc.sock")
    result = client.request("flush_dns", confirmed=True)
    assert result["status"] == "ok"
    assert mock_raw.call_count == 2
    privileged_call = mock_raw.call_args_list[1].args[1]
    assert privileged_call["confirmed"] is True
    assert privileged_call["session_token"] == "abc"