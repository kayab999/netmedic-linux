"""F2: the VPN installer is vendored, pinned, and never downloaded.

The installer bytes live in the repository, the helper reads them only from
a fixed root-owned path selected by ``script_id``, and the SHA256 of the
vendored file is the single trust anchor.
"""

import hashlib
from pathlib import Path

import pytest

from netmedic.helper_verbs import (
    PINNED_VPN_INSTALL_SHA256,
    VPN_SCRIPT_IDS,
    VPN_SCRIPT_PATHS,
    VerbValidationError,
    plan_verb,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "netmedic" / "netmedic" / "data" / "vpn"
VENDORED_SCRIPT = VENDOR_DIR / "openvpn-install.sh"


# --------------------------------------------------------------------------
# Vendored bytes + provenance
# --------------------------------------------------------------------------


def test_vendored_installer_matches_pin() -> None:
    """The file in the repo IS the trust anchor: sha256(file) == pin."""
    assert VENDORED_SCRIPT.is_file(), f"missing vendored installer: {VENDORED_SCRIPT}"
    digest = hashlib.sha256(VENDORED_SCRIPT.read_bytes()).hexdigest()
    assert digest == PINNED_VPN_INSTALL_SHA256


def test_vendored_installer_is_a_bash_script() -> None:
    first = VENDORED_SCRIPT.read_bytes().split(b"\n", 1)[0]
    assert first.startswith(b"#!") and b"bash" in first


def test_provenance_records_commit_hash_and_license() -> None:
    text = (VENDOR_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "9c966d4d043a0340503d6df577aa174a68468aed" in text
    assert PINNED_VPN_INSTALL_SHA256 in text
    assert "MIT" in text
    license_text = (VENDOR_DIR / "LICENSE.openvpn-install").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Stanislas Lange" in license_text


def test_operator_has_no_runtime_download_code() -> None:
    """F2: the daemon must not fetch the installer (even as a fallback)."""
    text = (REPO_ROOT / "netmedic" / "netmedic" / "operators" / "vpn" / "angristan.py").read_text(
        encoding="utf-8"
    )
    assert "curl" not in text
    assert "raw.githubusercontent.com" not in text


def test_script_ids_resolve_to_fixed_root_paths() -> None:
    assert VPN_SCRIPT_IDS == frozenset({"openvpn-install"})
    assert VPN_SCRIPT_PATHS == {
        "openvpn-install": "/usr/lib/netmedic/scripts/openvpn-install.sh"
    }
    for path in VPN_SCRIPT_PATHS.values():
        assert path.startswith("/usr/lib/netmedic/scripts/")
        assert ".." not in path


# --------------------------------------------------------------------------
# Typed VPN verbs (Fase 3) — no caller path/hash/env
# --------------------------------------------------------------------------


def test_vpn_run_script_removed() -> None:
    with pytest.raises(VerbValidationError, match="Unknown"):
        plan_verb("vpn-run-script", {"script_id": "openvpn-install"})


def test_plan_vpn_install_defaults() -> None:
    plan = plan_verb("vpn-install", {})
    assert plan.commands == [
        ["__vpn_cli__", "install", "--port", "1194", "--protocol", "udp",
         "--dns", "cloudflare", "--no-client-ipv6", "--client", "client"]
    ]


def test_plan_vpn_install_validates_port() -> None:
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-install", {"port": 0})
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-install", {"port": 70000})


def test_plan_vpn_install_validates_protocol_and_dns() -> None:
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-install", {"protocol": "icmp"})
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-install", {"dns": "nope"})


def test_plan_vpn_install_ipv6_flag() -> None:
    plan = plan_verb("vpn-install", {"client_ipv6": True})
    assert "--client-ipv6" in plan.commands[0]
    assert "--no-client-ipv6" not in plan.commands[0]


def test_plan_vpn_add_client() -> None:
    plan = plan_verb("vpn-add-client", {"name": "laptop"})
    assert plan.commands == [["__vpn_cli__", "client", "add", "laptop"]]


def test_plan_vpn_add_client_invalid_name() -> None:
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-add-client", {"name": "bad name!"})


def test_plan_vpn_revoke_client() -> None:
    plan = plan_verb("vpn-revoke-client", {"name": "laptop"})
    assert plan.commands == [["__vpn_cli__", "client", "revoke", "laptop", "--force"]]


def test_plan_vpn_revoke_client_invalid_name() -> None:
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-revoke-client", {"name": "../x"})


def test_plan_rejects_caller_supplied_script_path() -> None:
    """F3: no verb accepts a caller script path."""
    for verb in ("vpn-install", "vpn-add-client", "vpn-revoke-client"):
        args = {"name": "laptop"} if "client" in verb else {}
        with pytest.raises(VerbValidationError):
            plan_verb(verb, {**args, "script": "/tmp/x.sh"})  # noqa: S108


# --------------------------------------------------------------------------
# Installers ship the vendored file to the fixed root path
# --------------------------------------------------------------------------


def test_policy_installer_copies_vendored_script_root_owned() -> None:
    text = (REPO_ROOT / "scripts" / "install-polkit-policy.sh").read_text(encoding="utf-8")
    assert "netmedic/netmedic/data/vpn/openvpn-install.sh" in text
    # LIB_DIR is resolved above to /usr/lib/netmedic; the fixed subdir is scripts.
    assert 'SCRIPTS_DIR="$LIB_DIR/scripts"' in text
    assert "install -o root -g root -m 0644" in text


def test_debian_rules_install_vendored_script() -> None:
    text = (REPO_ROOT / "packaging" / "debian" / "rules").read_text(encoding="utf-8")
    assert "netmedic/netmedic/data/vpn/openvpn-install.sh" in text
    assert "debian/netmedic/usr/lib/netmedic/scripts/" in text


def test_pyproject_ships_vendored_data() -> None:
    text = (REPO_ROOT / "netmedic" / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.package-data]" in text
    assert "data/vpn/*" in text
