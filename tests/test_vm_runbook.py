"""Guardian: VM evidence tooling must target the shipped release and stay honest."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_obsolete_v1_6_verifier_removed() -> None:
    assert not (ROOT / "scripts" / "vm_verify_v1.6.1.sh").exists()


def test_runbook_does_not_return_mocked_results() -> None:
    text = (ROOT / "scripts" / "runbook_vm_evidence.py").read_text(encoding="utf-8")
    for marker in ("MagicMock", "Row 1 PASS", "Row 2 PASS"):
        assert marker not in text, f"runbook still fakes evidence: {marker}"


def test_runbook_checks_current_release_inputs() -> None:
    text = (ROOT / "scripts" / "runbook_vm_evidence.py").read_text(encoding="utf-8")
    for marker in (
        "HELPER_VERSION",
        "PINNED_VPN_INSTALL_SHA256",
        "pkaction",
        "restart-adapter",
        "change-dns",
        "VM_CHECKLIST",
    ):
        assert marker in text, f"runbook does not cover {marker}"
