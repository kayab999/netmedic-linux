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