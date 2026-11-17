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
