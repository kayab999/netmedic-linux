import hashlib

import pytest

import netmedic.helper_main as hm
from netmedic.system import CommandRunner


def test_command_redaction():
    """Verifica que los secretos no se logueen en texto plano."""
    cmd = ["mytool", "--password", "secret123", "--token=xyz789", "normal_arg"]
    redacted = CommandRunner._redact_command(cmd)

    assert "secret123" not in redacted
    assert "xyz789" not in redacted
    assert "--password <REDACTED>" in redacted
    assert "--token=<REDACTED>" in redacted
    assert "normal_arg" in redacted


def test_vendored_installer_tamper_is_refused(tmp_path, monkeypatch):
    """F2: the root helper aborts when the vendored bytes differ from the pin."""
    script = tmp_path / "openvpn-install.sh"
    script.write_text("#!/bin/bash\necho 'I am malicious'")
    script.chmod(0o644)
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(script))

    # Do not patch the pin: these bytes cannot match the vendored installer.
    with pytest.raises(hm.StagingError, match="integrity"):
        hm._read_vpn_script("openvpn-install")


def test_vendored_installer_matching_pin_is_accepted(tmp_path, monkeypatch):
    """F2: bytes matching the pin are the only ones the helper will read."""
    content = b"#!/bin/bash\necho ok\n"
    script = tmp_path / "openvpn-install.sh"
    script.write_bytes(content)
    script.chmod(0o644)
    digest = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(hm, "PINNED_VPN_INSTALL_SHA256", digest)
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(script))

    assert hm._read_vpn_script("openvpn-install") == content

def test_command_result_artifact_not_in_repr() -> None:
    """N3: the privileged artifact must not leak via repr/str/logging."""
    import logging
    from io import StringIO

    from netmedic.models import CommandResult

    secret = "-----BEGIN CERTIFICATE-----\nLEAKED-KEY-MATERIAL\n-----END CERTIFICATE-----"  # noqa: S105
    res = CommandResult(True, 0, "ok", "", [], artifact=secret)
    assert secret not in repr(res)
    assert secret not in str(res)

    buf = StringIO()
    handler = logging.StreamHandler(buf)
    log = logging.getLogger("netmedic.test.n3")
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    try:
        log.exception("boom: %r", res)
    finally:
        log.removeHandler(handler)
    assert secret not in buf.getvalue()

