"""Resolve install-time asset paths (icons, docs)."""
from __future__ import annotations

from pathlib import Path


def resolve_app_icon_path() -> Path | None:
    """Return the NetMedic PNG icon if present on disk."""
    module_dir = Path(__file__).resolve().parent
    candidates = (
        module_dir.parents[1] / "assets" / "netmedic.png",
        Path.home() / ".local/share/icons/hicolor/256x256/apps/netmedic.png",
        Path.home() / ".local/share/icons/netmedic.png",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def resolve_manual_path() -> Path | None:
    """Return the user manual path when running from a source checkout."""
    module_dir = Path(__file__).resolve().parent
    manual = module_dir.parents[1] / "docs" / "MANUAL.md"
    return manual if manual.is_file() else None