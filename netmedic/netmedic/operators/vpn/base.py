from abc import abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from netmedic.models import NetResult
from netmedic.operators.base import BaseOperator

@dataclass
class VPNClient:
    name: str
    created_at: Optional[str] = None
    active: bool = True

class VPNOperator(BaseOperator):
    """
    Contrato específico para operadores de VPN.
    Extiende BaseOperator con gestión de clientes.
    """

    @abstractmethod
    def list_clients(self) -> NetResult:
        """
        Devuelve la lista de clientes configurados.
        NetResult.data debe ser List[VPNClient] si success=True.
        """
        pass

    @abstractmethod
    def add_client(self, name: str) -> NetResult:
        """
        Crea un nuevo cliente/perfil VPN.
        """
        pass

    @abstractmethod
    def revoke_client(self, name: str) -> NetResult:
        """
        Revoca/Elimina un cliente VPN existente.
        """
        pass
    
    @abstractmethod
    def get_service_name(self) -> str:
        """
        Nombre del servicio systemd asociado (si aplica).
        """
        pass
