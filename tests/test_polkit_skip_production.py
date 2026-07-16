from netmedic.polkit_auth import skip_polkit


def test_skip_polkit_requires_test_mode(monkeypatch):
    monkeypatch.delenv("NETMEDIC_TEST_MODE", raising=False)
    monkeypatch.setenv("NETMEDIC_SKIP_POLKIT", "1")
    assert skip_polkit() is False


def test_skip_polkit_honored_in_test_mode(monkeypatch):
    monkeypatch.setenv("NETMEDIC_TEST_MODE", "1")
    monkeypatch.setenv("NETMEDIC_SKIP_POLKIT", "1")
    assert skip_polkit() is True


def test_skip_polkit_off_by_default(monkeypatch):
    monkeypatch.delenv("NETMEDIC_TEST_MODE", raising=False)
    monkeypatch.delenv("NETMEDIC_SKIP_POLKIT", raising=False)
    assert skip_polkit() is False