"""Guardian for VERBS.md — rule §1: every verb must be documented."""
import json
import re
from pathlib import Path


def _parse_verbs_registry():
    """Parse the JSON block in VERBS.md §8 anchored by marker."""
    md_path = Path(__file__).resolve().parent.parent / "VERBS.md"
    text = md_path.read_text(encoding="utf-8")
    # E1: anchored marker required — eliminates false match on example JSON
    assert "<!-- netmedic:verbs-registry v1 -->" in text, "VERBS.md missing anchor <!-- netmedic:verbs-registry v1 -->"
    # Must have marker immediately before fence
    m = re.search(r"<!-- netmedic:verbs-registry v1 -->\s*```json\s*\n(.*?)\n```", text, re.DOTALL)
    assert m, "VERBS.md missing anchored machine registry ```json block after marker"
    data = json.loads(m.group(1))
    assert isinstance(data, list), "registry must be list"
    return data


def _collect_registered_verbs():
    """Collect actual verbs from code: helper_verbs + action_catalog."""
    from netmedic.helper_verbs import ALL_VERBS
    from netmedic.action_catalog import PRIVILEGED_ACTIONS, SAFE_ACTIONS

    # Internal helpers that are not IPC but still verbs
    helper_verbs = set(ALL_VERBS)
    ipc_priv = set(PRIVILEGED_ACTIONS)
    ipc_safe = set(SAFE_ACTIONS)
    # action_catalog internal _INTERNAL_ACTIONS are subset of SAFE but also helpers
    return helper_verbs, ipc_priv, ipc_safe


def test_every_catalog_verb_is_documented():
    helper_verbs, ipc_priv, ipc_safe = _collect_registered_verbs()
    registry = _parse_verbs_registry()
    doc_helper = {r["helper_verb"] for r in registry if r.get("helper_verb")}
    doc_ipc_priv = {r["ipc_action"] for r in registry if r.get("ipc_action") and r.get("catalog") == "privileged"}
    doc_ipc_safe = {r["ipc_action"] for r in registry if r.get("ipc_action") and r.get("catalog") == "safe"}

    for hv in sorted(helper_verbs):
        assert hv in doc_helper, f"helper verb '{hv}' sin fila en VERBS.md — regla §1"

    for ipc in sorted(ipc_priv):
        assert ipc in doc_ipc_priv, f"IPC privileged '{ipc}' sin fila en VERBS.md"

    for ipc in sorted(ipc_safe):
        assert ipc in doc_ipc_safe, f"IPC safe '{ipc}' sin fila en VERBS.md"


def test_no_doc_drift():
    helper_verbs, ipc_priv, ipc_safe = _collect_registered_verbs()
    all_actual = helper_verbs | ipc_priv | ipc_safe
    # Include internal iface verbs already in helper_verbs
    registry = _parse_verbs_registry()
    for row in registry:
        hv = row.get("helper_verb")
        ipc = row.get("ipc_action")
        if hv:
            assert hv in helper_verbs, f"doc drift: helper_verb '{hv}' no existe en helper_verbs.py"
        if ipc:
            # ipc_action may be null for internal iface verbs
            is_known = ipc in ipc_priv or ipc in ipc_safe or ipc in helper_verbs
            # Also allow null
            if ipc not in (None,):
                assert ipc in (ipc_priv | ipc_safe), f"doc drift: ipc_action '{ipc}' no registrado en action_catalog.py"


def test_unverified_requires_tag():
    registry = _parse_verbs_registry()
    for row in registry:
        has_post = bool(row.get("post_condition") and row.get("post_condition").strip())
        unverified = row.get("unverified", False)
        if not has_post:
            assert unverified is True, f"verb {row.get('verb')} sin post_condition debe tener tag unverified-by-design"
            assert row.get("justification"), f"verb {row.get('verb')} unverified sin justificación"
        # If unverified true, must have justification
        if unverified:
            assert row.get("justification"), f"verb {row.get('verb')} unverified-by-design sin justificación"


def test_registry_json_well_formed():
    registry = _parse_verbs_registry()
    # Ensure required fields — now file+symbol are required (E2 symbolic refs)
    for row in registry:
        assert "verb" in row
        assert "catalog" in row
        assert row["catalog"] in ("privileged", "safe", "internal")
        assert "file" in row, f"row {row.get('verb')} missing symbolic 'file' (E2)"
        assert "symbol" in row, f"row {row.get('verb')} missing symbolic 'symbol' (E2)"
        # file_line kept for human ref but not authoritative


def test_reference_liveness():
    """E2: symbolic file+symbol must exist — file:line is not authoritative."""
    registry = _parse_verbs_registry()
    root = Path(__file__).resolve().parent.parent
    for row in registry:
        file_rel = row.get("file")
        symbol = row.get("symbol")
        assert file_rel, f"row {row.get('verb')} missing file"
        assert symbol, f"row {row.get('verb')} missing symbol"
        path = root / file_rel
        assert path.is_file(), f"reference liveness: file not found {file_rel} for verb {row.get('verb')}"
        content = path.read_text(encoding="utf-8", errors="ignore")
        # Symbol must appear verbatim in file (verb string or function name)
        assert symbol in content, f"reference liveness: symbol '{symbol}' not found in {file_rel} for verb {row.get('verb')}"
        # E2: post_condition must not contain file:line refs (rotate silently)
        pc = row.get("post_condition") or ""
        assert not re.search(r"\.py:\d+", pc), f"post_condition for {row.get('verb')} still contains file:line, use symbolic file/symbol"


def test_post_condition_symbol_liveness():
    """E2: post_condition symbolic refs must be resolvable."""
    registry = _parse_verbs_registry()
    for row in registry:
        pc = row.get("post_condition") or ""
        assert not re.search(r"\.py:\d+", pc), f"post_condition for {row.get('verb')} still contains file:line, use symbolic file/symbol"
