"""Manual CLI client for the prototype (design track; needs a bus to run).

Usage (once a bus service exists in the v2.0 build track):
    python -m tools.dbus_prototype.cli flush-dns '{}'
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb")
    parser.add_argument("args_json", nargs="?", default="{}")
    parser.parse_args(argv)  # validated for --help; bus call needs a service

    try:
        from gi.repository import Gio  # noqa: F401
    except ImportError:
        print("PyGObject/Gio is required to talk to the bus", file=sys.stderr)
        return 2
    print(json.dumps({"error": "no bus service in the design track; see docs/DBUS_DESIGN.md"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
