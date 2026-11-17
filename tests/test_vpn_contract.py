"""Contract tests between NetMedic and the vendored installer (Fase 2b).

These tests do NOT mock the installer: they execute its ``--help`` (which
needs no root) and parse the accepted flags from the real vendored bytes.
"""

import re

import pytest
import subprocess
from pathlib import Path

from netmedic.helper_verbs import plan_verb, VerbValidationError

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


def test_typed_plans_emit_only_accepted_flags(accepted_flags: set[str]) -> None:
    """Fase 3: every flag the typed plans emit must be accepted by the script."""
    cases = [
        plan_verb("vpn-install", {}),
        plan_verb("vpn-install", {"client_ipv6": True}),
        plan_verb("vpn-add-client", {"name": "laptop"}),
        plan_verb("vpn-revoke-client", {"name": "laptop"}),
    ]
    for plan in cases:
        # First token after __vpn_cli__ is the subcommand (install/client);
        # flags are the remaining -- tokens.
        for token in plan.commands[0]:
            if token.startswith("--"):
                assert token in accepted_flags, f"unknown flag {token}"

def test_vpn_add_client_rejects_password() -> None:
    """N1: password must never travel via argv/cmdline."""
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-add-client", {"name": "laptop", "password": "secret"})

