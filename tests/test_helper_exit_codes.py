"""Helper exit codes must come from a structured field, not message text."""
from __future__ import annotations

import hashlib
import json

import pytest

import netmedic.helper_main as hm


@pytest.mark.parametrize(
    ("result", "expected_rc"),
    [
        ({"ok": False, "code": "integrity", "message": "rewritten failure"}, 3),
        ({"ok": False, "code": "cancelled", "message": "dismissed"}, 126),
        ({"ok": False, "code": "op_fail", "message": "boom"}, 1),
    ],
)
def test_main_maps_exit_code_from_code(
    monkeypatch: pytest.MonkeyPatch, capsys, result: dict, expected_rc: int
) -> None:
    monkeypatch.setattr(hm, "execute_plan", lambda plan, timeout=None: result)
    assert hm.main(["flush-dns", "--execute"]) == expected_rc
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["code"] == result["code"]


def test_main_does_not_map_integrity_from_message_text(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A rewritten message without a code must not become rc=3 by accident."""
    monkeypatch.setattr(
        hm,
        "execute_plan",
        lambda plan, timeout=None: {
            "ok": False,
            "message": "Security abort: Script integrity failure.",
        },
    )
    assert hm.main(["flush-dns", "--execute"]) == 1
    assert json.loads(capsys.readouterr().out.strip())["ok"] is False


def test_bad_args_carry_code(capsys) -> None:
    assert hm.main(["renew-ip", "--execute", "--json", "{}"]) == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["code"] == "bad_args"


def test_vpn_pin_mismatch_is_structured_integrity(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "openvpn-install.sh"
    src.write_bytes(b"#!/bin/sh\necho tampered\n")
    src.chmod(0o644)
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(src))

    result = hm._execute_vpn_cli(
        ["__vpn_cli__", "install"], timeout=10, staging_dir=str(tmp_path / "stage")
    )
    assert result["ok"] is False
    assert result["code"] == "integrity"
    assert "Security abort: Script integrity failure." in result["message"]


def test_vpn_staging_dir_error_is_operational(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "openvpn-install.sh"
    content = b"#!/bin/sh\necho ok\n"
    digest = hashlib.sha256(content).hexdigest()
    src.write_bytes(content)
    src.chmod(0o644)
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(src))
    monkeypatch.setattr(hm, "PINNED_VPN_INSTALL_SHA256", digest)

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    result = hm._execute_vpn_cli(
        ["__vpn_cli__", "install"], timeout=10, staging_dir=str(blocker)
    )
    assert result["ok"] is False
    assert result["code"] == "op_fail"
    assert "integrity" not in result["message"].lower()
