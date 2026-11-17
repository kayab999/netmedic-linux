"""Guard the repo-root import layout (F0).

The repository root has a ``netmedic/`` directory that is not a package
(source lives in ``netmedic/netmedic/``). Running ``python -m pytest`` from
the root puts the cwd on ``sys.path``, so a bare ``import netmedic`` finds
that outer directory as a namespace package and shadows the installed one:
``ImportError: cannot import name '__version__'``.

``pytest.ini`` pins ``pythonpath = netmedic`` so the real package wins in
both normal and ``editable_mode=strict`` installs. This test keeps the
setting from being dropped.
"""

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pytest_pythonpath_targets_package_dir() -> None:
    parser = configparser.ConfigParser()
    assert parser.read(REPO_ROOT / "pytest.ini"), "pytest.ini missing"
    raw = parser["pytest"]["pythonpath"]
    entries = raw.split()
    assert "netmedic" in entries, (
        "pytest.ini must set `pythonpath = netmedic` so the repo-root "
        f"`netmedic/` directory cannot shadow the package (got {entries!r})"
    )
