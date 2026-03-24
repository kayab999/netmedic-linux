from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
from netmedic.models import NetResult

class OperatorStatus(Enum):
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"

class BaseOperator(ABC):
    """
    Contrato base para cualquier operador de sistema externo gestionado por NetMedic.
    Define el ciclo de vida mínimo: verificar estado e instalar/reparar.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre legible del operador (ej: 'OpenVPN (Angristan)')"""
        pass

    @property
    @abstractmethod
    def slug(self) -> str:
        """Identificador único para uso interno (ej: 'vpn-angristan')"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Descripción breve de lo que hace este operador"""
        pass

    @abstractmethod
    def check_status(self) -> NetResult:
        """
        Verifica el estado actual del componente en el sistema.
        Debe devolver NetResult con message=OperatorStatus.value
        """
        pass

    @abstractmethod
    def install(self) -> NetResult:
        """
        Instala o repara el componente.
        Debe ser idempotente y seguro.
        """
        pass
