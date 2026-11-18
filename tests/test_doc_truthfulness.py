"""Guardian: docs must not claim IPC token/confirmed as root protection."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_no_false_ipc_root_claim() -> None:
    old_phrase = "Privileged IPC actions require PolicyKit authorization, session token, and `confirmed=true`"
    offenders = []
    for path in ROOT.rglob("*.md"):
        if "build" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if old_phrase in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"false IPC-root claim still present in: {offenders}"


def test_current_release_line_is_supported() -> None:
    """SECURITY.md must mark the shipped 1.x line as supported."""
    version_text = (ROOT / "netmedic" / "netmedic" / "__init__.py").read_text(
        encoding="utf-8"
    )
    version = re.search(r'^__version__ = "(\d+)\.(\d+)\.', version_text, re.M)
    assert version, "cannot read __version__"
    release_line = f"{version.group(1)}.{version.group(2)}.x"

    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    row = re.search(
        rf"^\|\s*{re.escape(release_line)}\s*\|\s*([^|]+)\|", security, re.M
    )
    assert row, f"SECURITY.md has no supported-versions row for {release_line}"
    assert row.group(1).strip().lower().startswith("yes"), (
        f"SECURITY.md does not mark {release_line} as Yes: {row.group(1).strip()!r}"
    )


def test_policy_installer_does_not_advertise_legacy_elevation() -> None:
    """The root installer must not suggest disabling the helper in production."""
    text = (ROOT / "scripts" / "install-polkit-policy.sh").read_text(encoding="utf-8")
    assert "NETMEDIC_ALLOW_LEGACY_ELEVATION" not in text
    assert "Force legacy" not in text
