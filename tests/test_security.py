import pytest
from netmedic.system import CommandRunner
from netmedic.operators.vpn.angristan import AngristanOperator
from unittest.mock import MagicMock, patch
from pathlib import Path

def test_command_redaction():
    """Verifica que los secretos no se logueen en texto plano."""
    cmd = ["mytool", "--password", "secret123", "--token=xyz789", "normal_arg"]
    redacted = CommandRunner._redact_command(cmd)
    
    assert "secret123" not in redacted
    assert "xyz789" not in redacted
    assert "--password <REDACTED>" in redacted
    assert "--token=<REDACTED>" in redacted
    assert "normal_arg" in redacted

@patch("netmedic.operators.vpn.angristan.Config.get_operators_dir")
def test_operator_integrity_failure(mock_dir, tmp_path):
    """Verifica que el operador aborte si el hash no coincide."""
    mock_dir.return_value = tmp_path
    op = AngristanOperator()
    
    # Crear un script falso
    script_file = tmp_path / "openvpn-install.sh"
    script_file.write_text("#!/bin/bash
echo 'I am malicious'")
    
    # El hash real de este texto no coincidirá con EXPECTED_SHA256
    assert op._verify_integrity() is False
    
    # Intentar listar clientes debería fallar por integridad
    res = op.check_status()
    assert res.success is False
    assert "integrity" in res.details.lower()

def test_operator_integrity_success(tmp_path, monkeypatch):
    """Verifica que el operador acepte el hash correcto."""
    from netmedic.config import Config
    monkeypatch.setattr(Config, "get_operators_dir", lambda: tmp_path)
    
    op = AngristanOperator()
    script_file = tmp_path / "openvpn-install.sh"
    
    # Mockear el hash esperado para que coincida con un contenido conocido
    content = b"correct content"
    expected_hash = "ed962e21051939109044d4f8f41121df0c90435905d8f370f1a233b49c719e06" # sha256 of 'correct content'
    monkeypatch.setattr(op, "EXPECTED_SHA256", expected_hash)
    
    script_file.write_bytes(content)
    
    assert op._verify_integrity() is True
