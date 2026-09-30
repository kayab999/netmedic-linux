"""M9: typing-config guardians (stdlib-only, no yaml import)."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _ini_sections():
    sections = []
    for line in (REPO / "mypy.ini").read_text().splitlines():
        m = re.fullmatch(r"\[(mypy-[A-Za-z0-9_.*-]+)\]", line.strip())
        if m:
            sections.append(m.group(1))
    return sections


def test_no_glob_allowlist_sections():
    """A glob with ignore_errors shadowed every strict section (m6-vacuity).

    Proven with a deliberate int-vs-str probe: with the glob present, even
    the probe passed. Per-file sections cannot overlap, so they cannot hide
    each other. The glob must never return.
    """
    for section in _ini_sections():
        assert ".*" not in section, f"glob section banned: [{section}]"


def test_ci_file_list_matches_strict_sections():
    """CI's Typecheck invocation and mypy.ini strict set must agree.

    The 8-vs-10 drift (CI named 10, config enforced 8) hid here: fix the
    mapping once, pin it with this test.
    """
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
    m = re.search(r"mypy --config-file mypy\.ini\s+((?:netmedic/\S+\.py\s*)+)", ci)
    assert m, "CI Typecheck invocation not found"
    ci_files = m.group(1).split()
    ci_modules = sorted("netmedic." + Path(f).stem if Path(f).parent.name == "netmedic"
                        else "netmedic." + Path(f).parent.name + "." + Path(f).stem
                        for f in ci_files)
    ini_text = (REPO / "mypy.ini").read_text()
    strict_sections = sorted(
        s[len("mypy-"):] for s in _ini_sections()
        if re.search(rf"\[{re.escape(s)}\]\nstrict\s*=\s*True", ini_text)
    )
    assert ci_modules == strict_sections, (
        f"CI checks {ci_modules} but strict sections are {strict_sections}"
    )


def test_strict_sections_have_no_ignore_errors():
    """ignore_errors on a strict file would re-create the vacuity silently."""
    ini_text = (REPO / "mypy.ini").read_text()
    for section in _ini_sections():
        block = re.search(rf"\[{re.escape(section)}\](.*?)(?=\n\[|\Z)", ini_text, re.DOTALL)
        assert block is not None
        body = block.group(1)
        if re.search(r"^strict\s*=\s*True", body, re.MULTILINE):
            assert "ignore_errors" not in body, f"[{section}] mixes strict with ignore_errors"
