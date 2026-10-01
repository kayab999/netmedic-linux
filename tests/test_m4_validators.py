"""M4: one validators module; strict DNS/iface/conn rules everywhere."""

import re
from pathlib import Path

import pytest

import netmedic.validators as V
from netmedic import helper_verbs

REPO = Path(__file__).resolve().parents[1]


def _verdict(fn, *args, **kwargs):
    try:
        return ("ok", fn(*args, **kwargs))
    except ValueError as exc:
        return ("err", str(exc))


def test_no_duplicate_dns_regex():
    """The octet-regex copy must not reappear in wired modules."""
    for rel in ("netmedic/netmedic/helper_verbs.py", "netmedic/netmedic/network.py",
                "netmedic/netmedic/ipc_actions.py", "netmedic_ai/param_validation.py"):
        text = (REPO / rel).read_text()
        assert "25[0-5]" not in text, f"duplicated DNS regex in {rel}"


def test_helper_uses_canonical_validators():
    """helper_verbs.validate_* agree with netmedic.validators on a battery."""
    battery = ["1.1.1.1", "8.8.8.8", "1.1.1.1\n", "01.01.01.01", "999.1.1.1",
               "not-an-ip", "", "wlan0", "-h", "--help", "-eth0",
               "a" * 15, "a" * 16, "../etc", "medicabcdef", "eth0",
               "-evil", "Wired connection 1", "x" * 128, "x" * 129]
    for value in battery:
        assert _verdict(helper_verbs.validate_dns, value) == _verdict(V.validate_dns, value), value
        assert _verdict(helper_verbs.validate_iface, value) == _verdict(V.validate_iface, value), value
        assert _verdict(helper_verbs.validate_conn_name, value) == _verdict(V.validate_conn_name, value), value
        assert _verdict(helper_verbs.validate_client_name, value) == _verdict(V.validate_client_name, value), value
        assert _verdict(helper_verbs.validate_service, value) == _verdict(V.validate_service, value), value


def test_dns_newline_rejected():
    """Audit-verified flaw: '1.1.1.1\\n' must fail (was accepted by .match)."""
    with pytest.raises(ValueError):
        V.validate_dns("1.1.1.1\n")
    with pytest.raises(ValueError):
        helper_verbs.validate_dns("1.1.1.1\n")


def test_dns_leading_zeros_rejected():
    """Ambiguous octal octets are not valid DNS server input."""
    with pytest.raises(ValueError):
        V.validate_dns("01.01.01.01")


def test_dns_canonical_ok():
    assert V.validate_dns("1.1.1.1") == "1.1.1.1"
    assert V.validate_dns("8.8.8.8") == "8.8.8.8"


def test_iface_leading_dash_rejected():
    """'-h'/'--help' must not reach an option slot of fixed root argv."""
    for bad in ("-h", "--help", "-eth0", "-"):
        with pytest.raises(ValueError):
            V.validate_iface(bad)
        with pytest.raises(ValueError):
            helper_verbs.validate_iface(bad)


def test_iface_dot_names_rejected():
    """N3: '.' and '..' pass the charset regex; the kernel would ENODEV,
    but the app validator must not rely on that."""
    for bad in (".", ".."):
        with pytest.raises(ValueError):
            V.validate_iface(bad)
        with pytest.raises(ValueError):
            helper_verbs.validate_iface(bad)


def test_iface_length_cap():
    assert V.validate_iface("a" * 15) == "a" * 15  # IFNAMSIZ-1
    with pytest.raises(ValueError):
        V.validate_iface("a" * 16)


def test_iface_medic_only_preserved():
    assert V.validate_iface("medicabcdef", medic_only=True) == "medicabcdef"
    with pytest.raises(ValueError, match="non-medic"):
        V.validate_iface("eth0", medic_only=True)


def test_conn_name_leading_dash_rejected():
    with pytest.raises(ValueError):
        V.validate_conn_name("-evil")
    with pytest.raises(ValueError):
        helper_verbs.validate_conn_name("-evil")
    assert V.validate_conn_name("Wired connection 1") == "Wired connection 1"
    assert V.validate_conn_name("x" * 128) == "x" * 128
    with pytest.raises(ValueError):
        V.validate_conn_name("x" * 129)


def test_service_allowlist_preserved():
    assert V.validate_service("openvpn-server@server.service")
    with pytest.raises(ValueError, match="allowlisted"):
        V.validate_service("ssh.service")


def test_verb_error_type_still_catchable():
    """system.py catches VerbValidationError; ValueError must also catch."""
    with pytest.raises(helper_verbs.VerbValidationError):
        helper_verbs.validate_iface("-h")
    with pytest.raises(ValueError):
        helper_verbs.validate_iface("-h")
    assert issubclass(helper_verbs.VerbValidationError, ValueError)


def test_ai_path_rejects_newline_dns():
    """The AI copy that motivated M4 now rejects '1.1.1.1\\n'."""
    from netmedic_ai.param_validation import validate_tool_params

    assert validate_tool_params("change_dns", {"server": "1.1.1.1"}) is None
    assert validate_tool_params("change_dns", {"server": "1.1.1.1\n"}) is not None
    assert validate_tool_params("vpn_reconnect", {"interface": "-h"}) is not None
    assert validate_tool_params("vpn_reconnect", {"interface": "wlan0"}) is None


def test_ipc_change_dns_rejects_newline():
    from netmedic.ipc_actions import _validate_dispatch_params

    assert _validate_dispatch_params("change_dns", {"server": "1.1.1.1"}) is None
    assert _validate_dispatch_params("change_dns", {"server": "1.1.1.1\n"}) is not None


def test_installer_ships_validators():
    """-I mode ignores PYTHONPATH: validators.py must be installed root-side."""
    text = (REPO / "scripts" / "install-polkit-policy.sh").read_text()
    assert "validators.py" in text
    assert re.search(r"install .*validators\.py.*PKG_DIR/validators\.py", text)


def test_network_medic_helper_delegates():
    from netmedic.network import NetworkMedic

    assert NetworkMedic.is_medic_virtual_iface("medicabcdef") is True
    assert NetworkMedic.is_medic_virtual_iface("eth0") is False
