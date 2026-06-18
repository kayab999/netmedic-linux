import os
from unittest.mock import patch

from netmedic.lifecycle import LifecycleManager


def test_stale_lock_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    lifecycle = LifecycleManager()

    lifecycle.lock_file.write_text("999999")
    lifecycle.lock_file.chmod(0o600)

    with patch.object(lifecycle, "_is_process_alive", return_value=False):
        with patch.object(lifecycle, "_try_acquire_lock", side_effect=[False, True]):
            assert lifecycle.acquire_lock() is True


def test_acquire_lock_success(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    lifecycle = LifecycleManager()

    assert lifecycle.acquire_lock() is True
    assert lifecycle.lock_file.exists()
    assert lifecycle.lock_file.read_text().strip() == str(os.getpid())

    lifecycle.cleanup()
    assert not lifecycle.lock_file.exists()