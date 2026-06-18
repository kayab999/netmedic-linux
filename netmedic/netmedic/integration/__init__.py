import logging
from typing import Iterable

from netmedic.operators.base import BaseOperator

logger = logging.getLogger(__name__)


def shutdown_operators(operators: Iterable[BaseOperator]) -> None:
    """Stops all registered operators during application shutdown."""
    for operator in operators:
        try:
            operator.stop()
        except Exception as exc:
            logger.error("Failed to stop operator %s: %s", operator.name, exc)