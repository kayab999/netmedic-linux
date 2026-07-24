"""Polkit subject construction and start_time helpers."""

from unittest.mock import patch

from netmedic.polkit_auth import (
    _process_subject_spec,
    check_authorization,
    process_start_time,
)


def test_process_start_time_self():
    import os

    st = process_start_time(os.getpid())
    assert st is not None
    assert st >= 0


def test_process_start_time_invalid():
    assert process_start_time(-1) is None
    assert process_start_time(0) is None


def test_process_subject_spec_includes_start_time():
    import os

    pid = os.getpid()
    uid = os.getuid()
    spec, start = _process_subject_spec(pid, uid)
    assert start is not None
    assert spec == f"{pid},{start},{uid}"


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
@patch("netmedic.polkit_auth.shutil.which", return_value="/usr/bin/pkcheck")
@patch("subprocess.run")
def test_pkcheck_uses_process_spec_with_start_time(mock_run, _which, _action, _skip):
    """When GI is unavailable, pkcheck gets pid,start_time,uid."""
    import os

    mock_run.return_value.returncode = 0
    pid = os.getpid()
    uid = os.getuid()
    start = process_start_time(pid)

    # Force the GI branch to fail so pkcheck path runs.
    with patch("netmedic.polkit_auth.process_start_time", return_value=start):
        # Make `import gi` raise so the except falls through to pkcheck.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "gi" or (name.startswith("gi.") if isinstance(name, str) else False):
                raise ImportError("forced")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            ok, err = check_authorization("flush_dns", uid, pid)

    assert ok is True
    assert err is None
    cmd = mock_run.call_args[0][0]
    assert "--process" in cmd
    proc_idx = cmd.index("--process") + 1
    assert cmd[proc_idx] == f"{pid},{start},{uid}"
    assert "--allow-user-interaction" in cmd


def test_new_for_owner_signature_is_pid_start_uid():
    """Document/verify GI signature used by production code."""
    import gi

    gi.require_version("Polkit", "1.0")
    from gi.repository import Polkit

    doc = Polkit.UnixProcess.new_for_owner.__doc__ or ""
    # pygobject docs: new_for_owner(pid:int, start_time:int, uid:int)
    assert "start_time" in doc
    assert "pid" in doc
