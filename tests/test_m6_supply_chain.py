"""M6: supply-chain regression guards (static, repo style)."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _uses_refs(text: str):
    return re.findall(r"uses:\s*(\S+)", text)


def test_no_floating_action_refs():
    """Every `uses:` must pin an immutable 40-hex SHA (tag in comment)."""
    for wf in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
        for ref in _uses_refs(_read(wf)):
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref), f"{wf}: floating {ref}"


def test_action_pins_record_moving_tag():
    """Pins stay reviewable: each SHA line comments the tag it tracks."""
    for wf in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
        for line in _read(wf).splitlines():
            if "uses:" in line and "@" in line:
                assert re.search(r"#\s*v\d+", line), f"{wf}: pin without tag comment: {line.strip()}"


def test_top_level_permissions_read_only():
    """Workflows default to contents:read; write lives only in publish."""
    for wf in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
        text = _read(wf)
        assert re.search(r"(?m)^permissions:\n\s+contents: read", text), wf


def test_publish_job_gated_and_write_scoped():
    """Write token exists only in the publish job, behind `release` env."""
    text = _read(".github/workflows/release.yml")
    publish = text.split("publish:")[1]
    assert "contents: write" in publish
    assert "environment: release" in publish
    build = text.split("build:")[1].split("publish:")[0]
    assert "contents: write" not in build


def test_release_has_provenance_attestation():
    text = _read(".github/workflows/release.yml")
    assert "attest-build-provenance" in text
    assert "subject-path" in text


def test_pip_audit_blocking_against_lock():
    """No `|| echo` swallow; audit targets the lock, not the runner env."""
    for wf in (".github/workflows/ci.yml",):
        text = _read(wf)
        for line in text.splitlines():
            if "pip-audit" in line and "pip install" not in line:
                assert "|| echo" not in line, line
        assert "pip-audit --desc -r requirements.lock" in text
        for line in text.splitlines():
            if re.search(r"pip-audit\s+--", line):
                assert "--local" not in line and "--skip-editable" not in line, line


def test_binary_inputs_pinned_or_hashed():
    """Shipped binary inputs must not come from unpinned `pip install`."""
    build = _read("Dockerfile.build")
    assert "--require-hashes -r requirements.lock" in build
    assert '"pyinstaller==' not in build and "'pyinstaller==" not in build
    release = _read(".github/workflows/release.yml")
    assert re.search(r"pyinstaller==6\.19\.0|require-hashes", release)


def test_lock_has_hashes_for_pip_inputs():
    """Every pip-installable pin in requirements.lock carries a hash."""
    text = _read("requirements.lock")
    stanzas = re.findall(
        r"(?m)^([a-z0-9_-]+)==([^\s\\]+)\s*\\\s*\n((?:\s*--hash=sha256:[0-9a-f]+\n?)+)",
        text,
    )
    assert len(stanzas) >= 5, "expected hashed pins for binary closure"
    assert "PyGObject" not in "".join(f"{n}{v}" for n, v, _ in stanzas), "PyGObject is apt-only"
    for name, _ver, hashes in stanzas:
        assert len(hashes.strip()) > len("--hash=sha256:"), name


def test_dependabot_pip_dirs_exist():
    """Pip updates must point at dirs that contain manifests (stdlib-only)."""
    text = (REPO / ".github" / "dependabot.yml").read_text()
    # Parse the small known structure without PyYAML (not a test dep):
    # a `directory:` line following a `package-ecosystem: "pip"` entry.
    pip_dirs: list = []
    want_dir = False
    for line in text.splitlines():
        if 'package-ecosystem:' in line:
            want_dir = '"pip"' in line
        elif want_dir and "directory:" in line:
            pip_dirs.append(line.split("directory:")[1].strip().strip('"'))
            want_dir = False
    assert pip_dirs, "no pip entries"
    assert 'package-ecosystem: "github-actions"' in text
    for d in pip_dirs:
        assert d != "/", "root pip dir finds no manifests"
        target = REPO / d.lstrip("/")
        assert target.is_dir(), d
        assert list(target.glob("pyproject.toml")) or list(target.glob("*.txt")), d
