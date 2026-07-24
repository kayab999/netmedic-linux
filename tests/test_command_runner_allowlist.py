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
