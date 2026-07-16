"""Registered application teardown callbacks (GUI, executors, operators)."""
from __future__ import annotations

import logging
from typing import Callable, List

logger = logging.getLogger(__name__)

_callbacks: List[Callable[[], None]] = []


def register(callback: Callable[[], None]) -> None:
    if callback not in _callbacks:
        _callbacks.append(callback)


def run_all() -> None:
    for callback in reversed(_callbacks):
        try:
            callback()
        except Exception as exc:
            logger.error("Teardown callback failed: %s", exc)


def clear() -> None:
    _callbacks.clear()