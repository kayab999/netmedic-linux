"""Resolve install-time asset paths (icons, docs)."""
from __future__ import annotations

import sys
from pathlib import Path


def _bundle_root() -> Path | None:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return None


def _source_repo_root() -> Path:
    module_dir = Path(__file__).resolve().parent
    return module_dir.parents[1]


def resolve_app_icon_path() -> Path | None:
    """Return the NetMedic PNG icon if present on disk."""
    bundle = _bundle_root()
    candidates = []
    if bundle is not None:
        candidates.append(bundle / "assets" / "netmedic.png")
    candidates.extend(
        (
            _source_repo_root() / "assets" / "netmedic.png",
            Path.home() / ".local/share/icons/hicolor/256x256/apps/netmedic.png",
            Path.home() / ".local/share/icons/netmedic.png",
        )
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def resolve_manual_path() -> Path | None:
    """Return the user manual path when available."""
    bundle = _bundle_root()
    candidates = []
    if bundle is not None:
        candidates.append(bundle / "docs" / "MANUAL.md")
    candidates.append(_source_repo_root() / "docs" / "MANUAL.md")
    for manual in candidates:
        if manual.is_file():
            return manual
    return None