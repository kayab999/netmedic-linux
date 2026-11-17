"""Contract tests between NetMedic and the vendored installer (Fase 2b).

These tests do NOT mock the installer: they execute its ``--help`` (which
needs no root) and parse the accepted flags from the real vendored bytes.
"""

import re
import subprocess
from pathlib import Path

import pytest

from netmedic.helper_verbs import plan_verb

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "netmedic" / "netmedic" / "data" / "vpn" / "openvpn-install.sh"


def _help_flags(*args: str) -> set[str]:
    """Return the set of flags the vendored script accepts for *args*."""
    proc = subprocess.run(  # noqa: S603, S607 (fixed vendored script path + --help; no caller input)
        ["bash", str(SCRIPT), *args, "--help"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,  # noqa: S603, S607 (fixed vendored script + --help only; no caller input)
    )
    assert proc.returncode == 0, proc.stderr
    return set(re.findall(r"(?<![\w])-{1,2}[A-Za-z][\w-]*", proc.stdout))


@pytest.fixture(scope="module")
def accepted_flags() -> set[str]:
    flags: set[str] = set()
    flags |= _help_flags("install")
    flags |= _help_flags("client", "add")
    flags |= _help_flags("client", "revoke")
    return flags


# Flags NetMedic intends to emit once Fase 3 lands (see docs/VPN_CONTRACT.md).
REQUIRED_FLAGS = frozenset(
    {"--port", "--protocol", "--dns", "--no-client-ipv6", "--output", "--force"}
)


def test_required_flags_exist_in_vendored_script(accepted_flags: set[str]) -> None:
    """The vendored installer must support every flag NetMedic needs."""
    missing = REQUIRED_FLAGS - accepted_flags
    assert not missing, f"vendored script lacks required flags: {sorted(missing)}"


@pytest.mark.xfail(
    strict=True,
    reason="Fase 3 not implemented: current plan still emits the legacy env interface",
)
def test_current_plan_emits_only_accepted_flags(accepted_flags: set[str]) -> None:
    """Red today: the current plan emits env assignments (DNS=3, ...), none of
    which are flags the vendored script accepts. Goes green when Fase 3 builds
    argv on install/client add/client revoke."""
    plan = plan_verb(
        "vpn-run-script",
        {
            "script_id": "openvpn-install",
            "env": {
                "APPROVE_INSTALL": "y",
                "APPROVE_IP": "y",
                "IPV6_SUPPORT": "n",
                "PORT_CHOICE": "1",
                "PROTOCOL_CHOICE": "1",
                "DNS": "3",
                "COMPRESSION_ENABLED": "n",
                "CUSTOMIZE_ENC": "n",
                "MENU_OPTION": "1",
                "CLIENT": "laptop",
                "PASS": "1",
            },
        },
    )
    emitted = plan.commands[0][2:]
    bad = [token for token in emitted if token not in accepted_flags]
    assert not bad, f"plan emits tokens the script does not accept: {bad}"

