"""Guardian: docs must not claim IPC token/confirmed as root protection."""
import base64
import hashlib
import re
from pathlib import Path

from netmedic.helper_verbs import HELPER_VERSION

ROOT = Path(__file__).resolve().parent.parent

RELEASE_KEY_FINGERPRINT = "8C1BA036E834F3235593561C1A83A6D7885575E6"


def _public_key_fingerprint(armored: str) -> str:
    """Return the v4 fingerprint of the first public-key packet (no gpg needed)."""
    match = re.search(
        r"-----BEGIN PGP PUBLIC KEY BLOCK-----\r?\n\r?\n(.*?)"
        r"-----END PGP PUBLIC KEY BLOCK-----",
        armored,
        re.S,
    )
    assert match, "not an armored public key block"
    body = "".join(
        line
        for line in match.group(1).splitlines()
        if line and not line.startswith("=")
    )
    raw = base64.b64decode(body)
    # Old-format public-key packet: 0x99, 2-byte length, then the key body.
    assert raw[0] == 0x99, f"unexpected packet tag byte: {raw[0]:#04x}"
    length = int.from_bytes(raw[1:3], "big")
    # OpenPGP v4 fingerprints are defined as SHA-1 over the key packet.
    return hashlib.sha1(raw[: 3 + length]).hexdigest().upper()  # noqa: S324


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


def test_release_signing_key_is_published_and_verifiable() -> None:
    """SECURITY.md and the committed key must agree on the real fingerprint."""
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert RELEASE_KEY_FINGERPRINT in security
    assert "docs/RELEASE_KEY.asc" in security
    assert "gpg --verify SHA256SUMS.asc SHA256SUMS" in security
    assert "sha256sum -c SHA256SUMS" in security

    key_path = ROOT / "docs" / "RELEASE_KEY.asc"
    assert key_path.is_file(), "docs/RELEASE_KEY.asc is missing"
    key_text = key_path.read_text(encoding="utf-8")
    assert key_text.lstrip().startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----")
    assert key_text.rstrip().endswith("-----END PGP PUBLIC KEY BLOCK-----")
    assert "PRIVATE KEY" not in key_text
    assert _public_key_fingerprint(key_text) == RELEASE_KEY_FINGERPRINT


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
    # Per-verb wrappers: pkexec 0.105 matches on exec.path only.
    assert "helper-<verb>" in text
    assert "per-verb" in lower
    assert "does **not** perform a second polkit check" in lower
    assert "65,536" in text


def test_ai_module_is_declared_experimental_and_out_of_scope() -> None:
    """Optional AI must not look like a supported 1.9.0 surface."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "experimental" in readme.lower()
    assert "outside the supported 1.9.0 surface" in readme

    ai_doc = (ROOT / "docs" / "AI_SUPPLY_CHAIN.md").read_text(encoding="utf-8")
    assert "experimental and outside the supported 1.9.0 surface" in ai_doc
    assert "NETMEDIC_AI_MODEL_DIR" in ai_doc
    assert "admin-owned" in ai_doc
    assert "not writable by the user" in ai_doc
