"""Guardian: no test may construct a real modal Gtk dialog.

Real Gtk.MessageDialog/Dialog/AboutDialog .run() blocks forever under xvfb
(and segfaults off-main-thread headless). Dialogs in tests must be patch()
mocks — every current reference is a patch() string; this test keeps it so.
"""
import re
from pathlib import Path

_DIALOG_CTOR = re.compile(r"Gtk\.(MessageDialog|Dialog|AboutDialog)\s*\(")


def test_no_real_modal_dialogs():
    tests_dir = Path(__file__).resolve().parent
    offenders = []
    for path in sorted(tests_dir.glob("test_*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "patch(" in line:
                continue
            if _DIALOG_CTOR.search(line):
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, f"real modal dialogs in tests (mock them): {offenders}"
