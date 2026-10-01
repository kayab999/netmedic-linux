from unittest.mock import patch

from netmedic.polkit_auth import check_authorization


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
def test_polkit_denies_missing_peer(mock_action, _mock_skip):
    ok, err = check_authorization("flush_dns", uid=-1, pid=-1)
    assert ok is False
    assert "peer" in (err or "").lower()


@patch("netmedic.polkit_auth.skip_polkit", return_value=True)
def test_polkit_skip_env_allows(_mock_skip):
    ok, err = check_authorization("flush_dns", uid=1000, pid=1)
    assert ok is True
    assert err is None


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value=None)
def test_polkit_unknown_action_mapping(_mock_action, _mock_skip):
    ok, err = check_authorization("unknown_action", uid=1000, pid=1)
    assert ok is False
    assert "mapped" in (err or "").lower()


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
@patch("netmedic.polkit_auth.shutil.which", return_value="/usr/bin/pkcheck")
@patch("subprocess.run")
def test_polkit_pkcheck_success(mock_run, _which, _action, _skip):
    mock_run.return_value.returncode = 0
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert ok is True
    assert err is None


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
@patch("netmedic.polkit_auth.shutil.which", return_value="/usr/bin/pkcheck")
@patch("subprocess.run")
def test_polkit_pkcheck_denied(mock_run, _which, _action, _skip):
    mock_run.return_value.returncode = 1
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert ok is False
    assert "denied" in (err or "").lower()


def _no_gi(monkeypatch):
    """Force the pkcheck fallback regardless of installed typelibs."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "gi" or (isinstance(name, str) and name.startswith("gi.")):
            raise ImportError("forced")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
@patch("netmedic.polkit_auth.shutil.which", return_value="/usr/bin/pkcheck")
@patch("subprocess.run")
def test_polkit_pkcheck_needs_agent(mock_run, _which, _action, _skip, monkeypatch):
    _no_gi(monkeypatch)
    mock_run.return_value.returncode = 127
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert ok is False
    assert "pkttyagent" in (err or "").lower() or "interactive" in (err or "").lower()


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
@patch("netmedic.polkit_auth.shutil.which", return_value="/usr/bin/pkcheck")
@patch("subprocess.run")
def test_polkit_pkcheck_timeout(mock_run, _which, _action, _skip, monkeypatch):
    import subprocess

    _no_gi(monkeypatch)
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=5)
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert ok is False
    assert "timed out" in (err or "").lower()


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
@patch("netmedic.polkit_auth.shutil.which", return_value="/usr/bin/pkcheck")
@patch("subprocess.run")
def test_polkit_pkcheck_oserror(mock_run, _which, _action, _skip, monkeypatch):
    _no_gi(monkeypatch)
    mock_run.side_effect = OSError("noexec")
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert ok is False
    assert "failed" in (err or "").lower()


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
@patch("netmedic.polkit_auth.shutil.which", return_value=None)
def test_polkit_pkcheck_missing(_which, _action, _skip, monkeypatch):
    _no_gi(monkeypatch)
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert ok is False
    assert "unavailable" in (err or "").lower()


def _fake_gi(monkeypatch, authorized, *, owner_raises=False):
    """Inject a fake gi.repository.Polkit (works with or without typelib)."""
    import sys
    import types
    from unittest.mock import MagicMock

    result = MagicMock()
    result.get_is_authorized.return_value = authorized
    authority = MagicMock()
    authority.check_authorization_sync.return_value = result
    authority_cls = MagicMock()
    authority_cls.get_sync.return_value = authority
    unix_process = MagicMock()
    if owner_raises:
        unix_process.new_for_owner.side_effect = AttributeError("old pygobject")
    flags = types.SimpleNamespace(ALLOW_USER_INTERACTION=1, NONE=0)
    polkit_mod = types.SimpleNamespace(
        Authority=authority_cls, UnixProcess=unix_process,
        CheckAuthorizationFlags=flags,
    )
    repo_mod = types.ModuleType("gi.repository")
    repo_mod.Polkit = polkit_mod
    gi_mod = types.ModuleType("gi")
    gi_mod.require_version = lambda *a, **k: None
    gi_mod.repository = repo_mod
    monkeypatch.setitem(sys.modules, "gi", gi_mod)
    monkeypatch.setitem(sys.modules, "gi.repository", repo_mod)
    monkeypatch.setitem(sys.modules, "gi.repository.Polkit", polkit_mod)
    return authority


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
def test_polkit_gi_authorized(_action, _skip, monkeypatch):
    authority = _fake_gi(monkeypatch, authorized=True)
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert (ok, err) == (True, None)
    assert authority.check_authorization_sync.called


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
def test_polkit_gi_denied(_action, _skip, monkeypatch):
    _fake_gi(monkeypatch, authorized=False)
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert ok is False
    assert "denied" in (err or "").lower()


@patch("netmedic.polkit_auth.skip_polkit", return_value=False)
@patch("netmedic.polkit_auth.polkit_action_for", return_value="com.kayab.netmedic.flush-dns")
def test_polkit_gi_owner_fallback(_action, _skip, monkeypatch):
    """Old pygobject without new_for_owner falls back to new(pid)."""
    _fake_gi(monkeypatch, authorized=True, owner_raises=True)
    ok, err = check_authorization("flush_dns", uid=1000, pid=1234)
    assert (ok, err) == (True, None)