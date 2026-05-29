import logging
from typing import Dict
from netmedic.models import NetResult
from netmedic.system import CommandRunner
from netmedic.operators.base import BaseOperator, OperatorStatus

logger = logging.getLogger(__name__)

class WifiOperator(BaseOperator):
    @property
    def name(self) -> str:
        return "Wi-Fi Diagnostics"

    @property
    def slug(self) -> str:
        return "wifi-diagnostics"

    @property
    def description(self) -> str:
        return "Escaneo y análisis de congestión de redes Wi-Fi."

    def check_status(self) -> NetResult:
        # Chequeo rápido de disponibilidad
        status = CommandRunner.run(["nmcli", "general", "status"])
        if not status.success:
            return NetResult(self.name, False, OperatorStatus.ERROR.value)
        return NetResult(self.name, True, OperatorStatus.RUNNING.value)

    def install(self) -> NetResult:
        return NetResult(self.name, True, "Operador listo.")

    def stop(self) -> None:
        logger.info("WifiOperator detenido.")

    def scan_congestion(self) -> NetResult:
        """
        Escanea las redes Wi-Fi cercanas usando nmcli y determina
        la congestión de los canales.
        """
        # ... (rest of implementation unchanged)
        res = CommandRunner.run(["nmcli", "-t", "-f", "SSID,CHAN,SIGNAL", "device", "wifi", "list"])
        
        if not res.success:
            return NetResult(self.name, False, "Fallo al escanear redes Wi-Fi.", details=res.stderr)

        channels: Dict[str, int] = {}
        target_channels = ['1', '6', '11'] # Canales 2.4GHz no superpuestos estándar
        
        for line in res.stdout.splitlines():
            if not line: continue
            # nmcli -t usa ':' como delimitador por defecto
            parts = line.split(':')
            if len(parts) >= 2:
                chan = parts[1]
                if chan.isdigit():
                    channels[chan] = channels.get(chan, 0) + 1

        if not channels:
            return NetResult(self.name, True, "No se encontraron redes Wi-Fi cercanas.")

        # Buscar el más congestionado
        most_congested = max(channels, key=channels.get)
        count = channels[most_congested]
        
        # Básica recomendación 2.4Ghz
        recommended = "Desconocido"
        min_count = float('inf')
        for tc in target_channels:
            c = channels.get(tc, 0)
            if c < min_count:
                min_count = c
                recommended = tc

        msg = f"Canal más congestionado: {most_congested} ({count} redes). Canal recomendado: {recommended}."
        return NetResult(self.name, True, msg, data=channels)
