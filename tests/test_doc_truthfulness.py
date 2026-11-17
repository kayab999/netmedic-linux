"""Guardian: docs must not claim IPC token/confirmed as root protection."""
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
