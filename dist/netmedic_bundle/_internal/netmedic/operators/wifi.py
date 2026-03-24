import logging
from typing import Dict
from netmedic.models import NetResult
from netmedic.system import CommandRunner

logger = logging.getLogger(__name__)

class WifiOperator:
    @property
    def name(self) -> str:
        return "Wi-Fi Diagnostics"

    def scan_congestion(self) -> NetResult:
        """
        Escanea las redes Wi-Fi cercanas usando nmcli y determina
        la congestión de los canales.
        """
        # Chequeo rápido de disponibilidad
        status = CommandRunner.run(["nmcli", "general", "status"])
        if not status.success:
            return NetResult(self.name, False, "NetworkManager (nmcli) no está disponible.")

        # -t = tabular, -f campos
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
