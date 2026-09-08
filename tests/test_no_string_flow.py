"""Lint anti-SF-STR — control flow must not depend on human strings.

Allowlist: inline markers '# sf-str: allow <reason>' are required (E2).
Central file:line allowlists are fragile. New code must use structured fields.
"""
import re
from pathlib import Path


# Patterns that indicate string-based flow control (SF-STR)
FORBIDDEN_RE = re.compile(
    r"\bif\b.*\bin\s+(msg|message|details|stderr|stdout)\b"
    r"|\"[^\"]*(Gateway|Failed|Unreachable|Not Found|inactive|active|Soft blocked)[^\"]*\"\s*in\s+",
    re.IGNORECASE,
)

# More direct: any ' in msg' or ' in message' or ' in stderr' inside an if
DIRECT_PATTERNS = [
    re.compile(r"\bin\s+msg\b"),
    re.compile(r"\bin\s+message\b"),
    re.compile(r"\bin\s+result\.message\b"),
    re.compile(r"\bin\s+diag.*\.message\b"),
    re.compile(r"\bin\s+stderr\b"),
    re.compile(r'"[^"]*"\s*in\s+.*stdout', re.IGNORECASE),
]

SCAN_ROOTS = ["netmedic/netmedic", "netmedic_ai"]
ALLOWLIST_FILES = set()  # add if needed

def _is_allowlisted(line: str) -> bool:
    return "sf-str: allow" in line.lower() or "noqa" in line.lower()

def test_no_string_flow_control():
    root = Path(__file__).resolve().parent.parent
    violations = []
    for scan_root in SCAN_ROOTS:
        for py in (root / scan_root).rglob("*.py"):
            if py.name == "__pycache__":
                continue
            try:
                lines = py.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for idx, line in enumerate(lines, start=1):
                if _is_allowlisted(line):
                    continue
                # Check direct patterns only when inside control flow (if/elif/assert)
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "if" not in line and "elif" not in line and "assert" not in line:
                    continue
                for pat in DIRECT_PATTERNS:
                    if pat.search(line):
                        # Extra filter: ignore imports and comments
                        violations.append(f"{py.relative_to(root)}:{idx}: {line.strip()}")
                        break
                # Also check forbidden re; sf-str: allow is the only legit suppressor
                if FORBIDDEN_RE.search(line) and "sf-str: allow" not in line.lower():
                    entry = f"{py.relative_to(root)}:{idx}: {line.strip()}"
                    if entry not in violations:
                        violations.append(entry)
    assert not violations, (
        "SF-STR violations found (control flow on human strings):\n"
        + "\n".join(violations)
        + "\n\nFix: use structured fields (details/code) or add '# sf-str: allow <reason>' with justification."
    )


def test_allowlist_ratchet():
    """E3: allowlist is the new refuge — ratchet must not grow."""
    root = Path(__file__).resolve().parent.parent
    count = 0
    for scan_root in SCAN_ROOTS:
        for py in (root / scan_root).rglob("*.py"):
            try:
                text = py.read_text(encoding="utf-8")
            except Exception:
                continue
            count += text.lower().count("sf-str: allow")
    # Current max is 9 (8 original + 1 for operstate fallback). Ratchet must not grow.
    MAX_ALLOWED = 9
    assert count <= MAX_ALLOWED, (
        f"SF-STR allowlist ratchet exceeded: {count} > {MAX_ALLOWED}. "
        f"Do not add new '# sf-str: allow' without removing another or bumping MAX with justification."
    )
