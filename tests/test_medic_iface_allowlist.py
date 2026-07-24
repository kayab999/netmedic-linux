"""Orphan/state interface names must not drive arbitrary ip link del."""

import json
from unittest.mock import patch

from netmedic.network import NetworkMedic


def test_is_medic_virtual_iface_allowlist():
    assert NetworkMedic.is_medic_virtual_iface("medicabcdef")
    assert NetworkMedic.is_medic_virtual_iface("medic000000")
    assert not NetworkMedic.is_medic_virtual_iface("eth0")
    assert not NetworkMedic.is_medic_virtual_iface("medicABC")  # uppercase
    assert not NetworkMedic.is_medic_virtual_iface("medicabcd")  # 4 hex
    assert not NetworkMedic.is_medic_virtual_iface("medicabcdefg")  # 7 hex
    assert not NetworkMedic.is_medic_virtual_iface("../eth0")


def test_sanitize_iface_list_drops_poison():
    cleaned = NetworkMedic._sanitize_iface_list(["eth0", "medicabcdef", 12, None, "wlan0"])
    assert cleaned == {"medicabcdef"}


def test_delete_medic_iface_refuses_non_medic():
    with patch("netmedic.network.CommandRunner.run") as mock_run:
        ok = NetworkMedic._delete_medic_iface("eth0")
        assert ok is False
        mock_run.assert_not_called()


def test_delete_medic_iface_allows_medic_name():
    with patch("netmedic.network.CommandRunner.run") as mock_run:
        mock_run.return_value.success = True
        ok = NetworkMedic._delete_medic_iface("medicabcdef")
        assert ok is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["ip", "link", "del", "medicabcdef"]


def test_reap_orphan_ignores_poisoned_state(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    poison = tmp_path / "created_ifaces.1.json"
    poison.write_text(json.dumps(["eth0", "medicabcdef"]), encoding="utf-8")

    with patch.object(NetworkMedic, "_is_process_alive", return_value=False):
        with patch.object(NetworkMedic, "_delete_medic_iface", return_value=True) as mock_del:
            medic = object.__new__(NetworkMedic)
            NetworkMedic._reap_orphan_iface_state(medic)
            called = [c.args[0] for c in mock_del.call_args_list]
            assert "medicabcdef" in called
            assert "eth0" not in called
