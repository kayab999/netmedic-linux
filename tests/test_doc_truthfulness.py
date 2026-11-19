"""Guardian: docs must not claim IPC token/confirmed as root protection."""
import re
from pathlib import Path

from netmedic.helper_verbs import HELPER_VERSION

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


def test_threat_model_states_current_release_line() -> None:
    """The threat model header must name the shipped release, not v1.6/v1.8."""
    text = (ROOT / "docs" / "THREAT_MODEL.md").read_text(encoding="utf-8")
    header = text.splitlines()[0]
    assert f"(v{HELPER_VERSION})" in header, header
    assert "reaffirmed v1.8" not in header
    assert "Bounded IPC acceptance" in text
    assert "Fail-closed helper version gate" in text


def test_privileged_helper_doc_states_current_release_line() -> None:
    """The helper design must describe the 1.9.0 contract, not a v1.5 target."""
    text = (ROOT / "docs" / "PRIVILEGED_HELPER.md").read_text(encoding="utf-8")
    header = text.splitlines()[0]
    assert f"v{HELPER_VERSION}" in header, header
    assert "v1.5 target" not in header
    assert "HELPER_VERSION" in text
    assert "keep_auth" in text
    assert "Version gate" in text
    assert "Installed layout and staging" in text


def test_ipc_api_separates_helper_and_legacy_modes() -> None:
    """IPC_API must not present Polkit as an IPC-layer check in helper mode."""
    text = (ROOT / "docs" / "IPC_API.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "helper mode" in lower
    assert "legacy mode" in lower
    assert "org.freedesktop.policykit.exec.argv1" in text or "exec.argv1" in text
    assert "does **not** perform a second polkit check" in lower
    assert "65,536" in text
