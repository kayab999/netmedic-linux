import json
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
        return "Scan and analyze nearby Wi-Fi channel congestion."

    def check_status(self) -> NetResult:
        status = CommandRunner.run(["nmcli", "general", "status"])
        if not status.success:
            return NetResult(self.name, False, OperatorStatus.ERROR.value)
        return NetResult(self.name, True, OperatorStatus.RUNNING.value)

    def install(self) -> NetResult:
        return NetResult(self.name, True, "Operator ready.")

    def stop(self) -> None:
        logger.info("WifiOperator stopped.")

    def _parse_channels(self, stdout: str) -> Dict[str, int]:
        channels: Dict[str, int] = {}
        for line in stdout.splitlines():
            if not line:
                continue
            chan = line.strip()
            if chan.isdigit():
                channels[chan] = channels.get(chan, 0) + 1
        return channels

    def _scan_json(self) -> Dict[str, int]:
        res = CommandRunner.run(
            ["nmcli", "--json", "auto", "-f", "SSID,CHAN", "device", "wifi", "list"]
        )
        if not res.success:
            return {}
        try:
            entries = json.loads(res.stdout)
        except json.JSONDecodeError:
            return {}
        channels: Dict[str, int] = {}
        for entry in entries:
            chan = str(entry.get("CHAN", "")).strip()
            if chan.isdigit():
                channels[chan] = channels.get(chan, 0) + 1
        return channels

    def scan_congestion(self) -> NetResult:
        channels = self._scan_json()
        if not channels:
            res = CommandRunner.run(["nmcli", "-t", "-f", "CHAN", "device", "wifi", "list"])
            if not res.success:
                return NetResult(self.name, False, "Failed to scan Wi-Fi networks.", details=res.stderr)
            channels = self._parse_channels(res.stdout)

        if not channels:
            return NetResult(self.name, True, "No nearby Wi-Fi networks found.")

        target_channels = ["1", "6", "11"]
        most_congested = max(channels, key=channels.get)
        count = channels[most_congested]

        recommended = "Unknown"
        min_count = float("inf")
        for tc in target_channels:
            c = channels.get(tc, 0)
            if c < min_count:
                min_count = c
                recommended = tc

        msg = (
            f"Most congested channel: {most_congested} ({count} networks). "
            f"Recommended 2.4 GHz channel: {recommended}."
        )
        return NetResult(self.name, True, msg, data=channels)