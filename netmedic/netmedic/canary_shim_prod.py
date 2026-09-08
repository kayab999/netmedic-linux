"""Canary production module for E4 — reads NetResult.success.

This module exists solely to verify that the DeprecationWarning guard
triggers for production code. It must stay in netmedic/ (not tests/) so
the immediate caller is not in tests.
"""
from netmedic.models import NetResult, ResultCode

def read_success_shim() -> bool:
    r = NetResult("Canary", True, "ok", code=ResultCode.OK)
    return r.success  # should emit DeprecationWarning → error via filterwarnings
