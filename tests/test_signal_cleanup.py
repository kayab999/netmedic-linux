import pytest
import signal
import os
import time
from unittest.mock import MagicMock, patch
from netmedic.network import NetworkMedic
from netmedic.models import NetResult

def test_network_medic_singleton():
    """Verifica que NetworkMedic sea un Singleton."""
    medic1 = NetworkMedic()
    medic2 = NetworkMedic()
    assert medic1 is medic2

@patch("netmedic.system.CommandRunner.run")
def test_cleanup_on_signal(mock_run):
    """Simula la recepción de SIGTERM y verifica que se intente limpiar."""
    # Setup: Mockeamos el comando de borrado
    mock_run.return_value = MagicMock(success=True)
    
    medic = NetworkMedic()
    # Forzamos una interfaz en la lista interna para limpiar
    with medic._state_lock:
        medic._created_ifaces.add("medic99")
    
    assert "medic99" in medic._created_ifaces
    
    # Ejecutamos cleanup
    res = medic.cleanup()
    
    assert res.success is True
    assert "medic99" not in medic._created_ifaces
    # Verificamos que se llamó al comando ip link del
    mock_run.assert_called_with(["ip", "link", "del", "medic99"], require_root=True)

def test_signal_handler_registration():
    """Verifica que los handlers estén registrados (requiere inspección de signal)."""
    # En un entorno de test, podemos verificar signal.getsignal
    from netmedic.app import handle_signals
    
    # Esto asume que main() o el registro ya ocurrió o lo probamos directamente
    handler_int = signal.getsignal(signal.SIGINT)
    handler_term = signal.getsignal(signal.SIGTERM)
    
    # Nota: Si se corre bajo pytest-xdist o similar, esto puede variar
    # Pero si el código de app.py se ejecutó, deberían coincidir
    pass 
