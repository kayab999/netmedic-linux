"""Canary for E4 — production read of .success must burst via global filter."""
import warnings

import pytest


def test_canary_success_shim_bursts():
    """If someone reintroduces net_res.success in production, suite must fail."""
    from netmedic.canary_shim_prod import read_success_shim

    # No simplefilter override — must burst via ini exactly as shipped (error last prevails)
    with pytest.raises(UserWarning, match="NetResult.success is deprecated"):
        read_success_shim()


def test_canary_allows_code_path():
    """Code path via .code must not warn."""
    from netmedic.models import NetResult, ResultCode

    r = NetResult("Canary", True, "ok", code=ResultCode.OK)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", DeprecationWarning)
        _ = r.code
        _ = r.message
        # No DeprecationWarning for .code
        assert not any(issubclass(x.category, DeprecationWarning) for x in w)
    assert r.code == ResultCode.OK
