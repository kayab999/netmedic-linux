"""Installed-helper contract: wrapper, pkexec annotations and dry-runs.

These checks need a real installation made by
``scripts/install-polkit-policy.sh`` and a running polkitd. They are opt-in so
the local unit suite stays untouched:

    NETMEDIC_INSTALLED_HELPER=1 pytest tests/test_installed_helper_contract.py

CI runs them in the ``helper-install-integration`` job. Interactive
authorization, destructive execution and rollback stay in the VM checklist;
this file only proves the installed contract without faking a root session.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from netmedic.action_catalog import ACTIONS, ALL_HELPER_VERBS
from netmedic.helper_verbs import HELPER_VERSION
from netmedic.system import CommandRunner

pytestmark = pytest.mark.skipif(
    os.environ.get("NETMEDIC_INSTALLED_HELPER") != "1",
    reason="requires an installed helper (NETMEDIC_INSTALLED_HELPER=1)",
)

HELPER = Path("/usr/libexec/netmedic/helper")
POLICY = Path("/usr/share/polkit-1/actions/com.kayab.netmedic.policy")
LIB_DIR = Path("/usr/lib/netmedic")

# Valid dry-run arguments for every verb. None of these executes anything.
DRY_RUN_ARGS: dict[str, dict[str, Any]] = {
    "flush-dns": {},
    "renew-ip": {"iface": "eth0", "mode": "nmcli"},
    "change-dns": {"server": "1.1.1.1", "connection": "Wired connection 1"},
    "restart-adapter": {"iface": "eth0"},
    "reset-stack": {},
    "toggle-firewall": {"action": "enable"},
    "vpn-list": {},
    "vpn-install": {},
    "vpn-add-client": {"name": "auditclient"},
    "vpn-revoke-client": {"name": "auditclient"},
    "vpn-start-service": {},
    "vpn-restart-service": {},
    "iface-del": {"iface": "medicabcdef"},
    "iface-add-dummy": {"iface": "medic000001"},
}

def _run(*argv: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (fixed wrapper path, no shell)
        [str(HELPER), *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _payload(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    lines = (proc.stdout or "").strip().splitlines()
    assert lines, f"helper produced no stdout (rc={proc.returncode}, stderr={proc.stderr!r})"
    data = json.loads(lines[-1])
    assert isinstance(data, dict)
    return data


def _policy_actions() -> dict[str, ET.Element]:
    # Root-owned installed policy, not untrusted input; ElementTree is enough.
    root = ET.parse(POLICY).getroot()  # noqa: S314
    return {action.get("id", ""): action for action in root.iter("action")}


def _annotation(action: ET.Element, key: str) -> str:
    for node in action.iter("annotate"):
        if node.get("key") == key:
            return (node.text or "").strip()
    return ""


def _default(action: ET.Element, key: str) -> str:
    for node in action.iter("defaults"):
        for child in node:
            if child.tag == key:
                return (child.text or "").strip()
    return ""


def test_installation_layout_is_root_owned() -> None:
    assert HELPER.is_file(), f"missing helper wrapper: {HELPER}"
    wrapper = HELPER.stat()
    assert wrapper.st_uid == 0
    assert stat.S_IMODE(wrapper.st_mode) == 0o755
    assert LIB_DIR.is_dir()
    installed_pkg = LIB_DIR / "netmedic"
    for name in ("helper_main.py", "helper_verbs.py", "validators.py", "action_catalog.py"):
        installed = installed_pkg / name
        assert installed.is_file(), f"missing installed module: {installed}"
        st = installed.stat()
        assert st.st_uid == 0, f"{installed} is not root-owned"
        assert stat.S_IMODE(st.st_mode) == 0o644, f"{installed} has unexpected mode"
    assert POLICY.is_file(), f"missing installed policy: {POLICY}"


def test_wrapper_reports_matching_version() -> None:
    proc = _run("--version")
    assert proc.returncode == 0, proc.stderr
    payload = _payload(proc)
    assert payload["ok"] is True
    assert payload["version"] == HELPER_VERSION


def test_wrapper_lists_every_verb() -> None:
    proc = _run("--list-verbs")
    assert proc.returncode == 0, proc.stderr
    payload = _payload(proc)
    assert payload["ok"] is True
    assert set(payload["verbs"]) == set(ALL_HELPER_VERBS)


def test_policy_registers_every_privileged_action() -> None:
    actions = _policy_actions()
    privileged = [spec for spec in ACTIONS if spec.polkit_id]
    assert len(privileged) == 12
    for spec in privileged:
        assert spec.polkit_id in actions, f"{spec.polkit_id} missing from installed policy"
        registered = subprocess.run(  # noqa: S603 (fixed binary, no shell)
            ["/usr/bin/pkaction", "--action-id", spec.polkit_id],
            capture_output=True,
            text=True,
            check=False,
        )
        assert registered.returncode == 0, (
            f"polkit does not see {spec.polkit_id}: {registered.stderr}"
        )
        action = actions[spec.polkit_id]
        expected_path = HELPER.parent / f"helper-{spec.helper_verb}"
        assert _annotation(
            action, "org.freedesktop.policykit.exec.path"
        ) == str(expected_path)
        # exec.argv1 is intentionally absent in the per-verb design.
        assert _annotation(action, "org.freedesktop.policykit.exec.argv1") is None
        assert _default(action, "allow_active") == (
            "auth_admin_keep" if spec.keep_auth else "auth_admin"
        )


@pytest.mark.parametrize("verb", sorted(ALL_HELPER_VERBS))
def test_dry_run_every_verb(verb: str) -> None:
    proc = _run(verb, "--dry-run", "--json", json.dumps(DRY_RUN_ARGS[verb]))
    assert proc.returncode == 0, f"{verb} dry-run failed: {proc.stderr}"
    payload = _payload(proc)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["verb"] == verb
    assert payload["commands"], f"{verb} planned no commands"


@pytest.mark.parametrize(
    ("argv", "needle"),
    [
        (("rm-rf", "--dry-run"), "Unknown verb"),
        (("renew-ip", "--dry-run", "--json", "{}"), "iface"),
        (("toggle-firewall", "--dry-run", "--json", '{"action":"maybe"}'), "enable"),
        (("vpn-list", "--dry-run", "--json", '{"index_path":"/etc/shadow"}'), "path"),
        (("vpn-install", "--dry-run", "--json", '{"script":"/tmp/x"}'), "script"),
        (("iface-del", "--dry-run", "--json", '{"iface":"eth0"}'), "non-medic"),
    ],
)
def test_wrapper_rejects_invalid_input(argv: tuple[str, ...], needle: str) -> None:
    proc = _run(*argv)
    assert proc.returncode == 2, proc.stderr
    payload = _payload(proc)
    assert payload["ok"] is False
    assert needle in (payload.get("message") or "")


def test_version_probe_accepts_installed_helper() -> None:
    assert CommandRunner._check_helper_version() is None


def test_version_probe_blocks_stale_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "stale-helper"
    stale.write_text(
        "#!/bin/sh\nprintf '%s\\n' '{\"ok\": true, \"version\": \"0.0.0-stale\"}'\n",
        encoding="utf-8",
    )
    stale.chmod(0o755)
    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path", staticmethod(lambda: stale)
    )
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "version mismatch" in error
    assert "install-polkit-policy" in error
