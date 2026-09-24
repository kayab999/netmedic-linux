from netmedic.system import CommandRunner


def test_root_allowlist_rejects_unknown_binary():
    err = CommandRunner._assert_root_command_allowed(["rm", "-rf", "/"])
    assert err is not None
    assert "allowlisted" in err.lower()


def test_root_allowlist_accepts_ip():
    assert CommandRunner._assert_root_command_allowed(["ip", "link", "del", "medicabcdef"]) is None


def test_root_allowlist_env_requires_script_path():
    assert CommandRunner._assert_root_command_allowed(["env", "FOO=1"]) is not None
    assert CommandRunner._assert_root_command_allowed(["env", "FOO=1", "/tmp/script.sh"]) is None


def test_root_allowlist_env_rejects_flags():
    assert CommandRunner._assert_root_command_allowed(["env", "-i", "script"]) is not None


def test_root_allowlist_rejects_shell():
    # P0 hardening: bash/sh removed — no legit elevated path needs a shell
    assert CommandRunner._assert_root_command_allowed(["bash", "-c", "id"]) is not None
    assert CommandRunner._assert_root_command_allowed(["sh", "-c", "id"]) is not None


def test_config_ignores_env_override_when_root(monkeypatch):
    from netmedic.config import Config

    monkeypatch.setenv("NETMEDIC_HELPER_PATH", "/tmp/evil-helper")
    monkeypatch.setenv("NETMEDIC_ALLOW_LEGACY_ELEVATION", "1")
    monkeypatch.setattr("os.geteuid", lambda: 0)
    # Must not honor attacker-controlled env in root context
    assert str(Config.get_helper_path()) != "/tmp/evil-helper"
    assert Config.allow_legacy_elevation() is False
