"""Packaging metadata: the core must not require GTK/PyGObject.

These tests read the installed distribution metadata, so they cover the same
``Requires-Dist`` fields consumed by pip from wheels and sdists. CI installs
the project before running the suite.
"""
from __future__ import annotations

import importlib.metadata as metadata

import pytest


def _requires() -> list[str]:
    try:
        meta = metadata.metadata("netmedic")
    except metadata.PackageNotFoundError:  # pragma: no cover - CI installs it
        pytest.skip("netmedic is not installed in this environment")
    return list(meta.get_all("Requires-Dist") or [])


def _is_extra(requirement: str) -> bool:
    return "extra ==" in requirement or "extra==" in requirement


def test_core_has_no_mandatory_dependencies() -> None:
    unconditional = [req for req in _requires() if not _is_extra(req)]
    assert unconditional == [], f"core must stay dependency-free: {unconditional}"


def test_gui_extra_declares_pygobject() -> None:
    gui = [req for req in _requires() if 'extra == "gui"' in req]
    assert gui, "the gui extra is missing from package metadata"
    assert any(req.lower().startswith("pygobject") for req in gui), gui


def test_ai_extra_is_preserved() -> None:
    ai = [req for req in _requires() if 'extra == "ai"' in req]
    assert any(req.lower().startswith("llama-cpp-python") for req in ai), ai
