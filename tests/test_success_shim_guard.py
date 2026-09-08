"""E4: shim .success must not be load-bearing for NetResult — Migrate consumers to .code.

Only the shim definition in models.py may define .success. Consumers in
tools/netmedic_mcp.py and netmedic_ai must use code. CommandResult.success
is legitimate low-level API and is allowlisted via file scope.
"""
import re
from pathlib import Path


def test_no_new_success_shim_usage():
    root = Path(__file__).resolve().parent.parent
    pattern = re.compile(r"\.success\b")
    violations = []
    # E4 scope: in-repo consumers that were migrated must stay migrated.
    # CommandResult.success in netmedic/netmedic is OK (low-level), so we
    # only guard the consumer layer: tools + netmedic_ai
    for scan_root in ["tools", "netmedic_ai"]:
        for py in (root / scan_root).rglob("*.py"):
            if py.name == "__pycache__":
                continue
            try:
                lines = py.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for idx, line in enumerate(lines, start=1):
                if "sf-success: allow" in line.lower():
                    continue
                if pattern.search(line):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    violations.append(f"{py.relative_to(root)}:{idx}: {line.strip()}")
    # Also guard NetResult.success in UI layer: new code must use code
    # Allowlist existing legitimate CommandResult checks via sf-success marker
    # For netmedic/netmedic/ui.py we check NetResult specifically
    ui_path = root / "netmedic/netmedic/ui.py"
    if ui_path.is_file():
        for idx, line in enumerate(ui_path.read_text(encoding="utf-8").splitlines(), start=1):
            if "sf-success: allow" in line.lower():
                continue
            if ".success" in line and "net_res" in line:
                violations.append(f"netmedic/netmedic/ui.py:{idx}: {line.strip()} (use .code)")
    assert not violations, (
        "E4: .success shim usage in consumer layer — must use .code (ResultCode):\n"
        + "\n".join(violations)
        + "\nMigrate to code or add '# sf-success: allow' with justification."
    )


def test_shim_mapping_documented():
    """Shim mapping must stay documented in models.py and VERBS.md."""
    root = Path(__file__).resolve().parent.parent
    verbs_text = (root / "VERBS.md").read_text(encoding="utf-8")
    assert "OK / EXECUTED" in verbs_text and "success" in verbs_text.lower(), "VERBS.md must document shim mapping"
    models_text = (root / "netmedic/netmedic/models.py").read_text(encoding="utf-8")
    assert "ResultCode" in models_text


def test_success_allowlist_ratchet():
    """E2/E4 symmetry: sf-success allow must not grow."""
    root = Path(__file__).resolve().parent.parent
    count = 0
    for scan_root in ["netmedic/netmedic", "tools", "netmedic_ai"]:
        for py in (root / scan_root).rglob("*.py"):
            try:
                text = py.read_text(encoding="utf-8")
            except Exception:
                continue
            count += text.lower().count("sf-success: allow")
    # After migration, only shim definition may need allow; current is 0
    MAX_ALLOWED = 2
    assert count <= MAX_ALLOWED, f"sf-success allowlist ratchet exceeded: {count} > {MAX_ALLOWED}"
