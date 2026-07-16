import logging
from typing import Iterable, List

from netmedic.operators.base import BaseOperator

logger = logging.getLogger(__name__)

_REGISTERED_OPERATORS: List[BaseOperator] = []


def register_operator(operator: BaseOperator) -> None:
    """Register a third-party operator for lifecycle management."""
    if operator not in _REGISTERED_OPERATORS:
        _REGISTERED_OPERATORS.append(operator)
        logger.debug("Registered operator: %s", operator.name)


def get_registered_operators() -> List[BaseOperator]:
    return list(_REGISTERED_OPERATORS)


def shutdown_operators(operators: Iterable[BaseOperator]) -> None:
    """Stops all registered operators during application shutdown."""
    seen = set()
    for operator in operators:
        if id(operator) in seen:
            continue
        seen.add(id(operator))
        try:
            operator.stop()
        except Exception as exc:
            logger.error("Failed to stop operator %s: %s", operator.name, exc)