"""Canary for E4 — production read of .success must warn (would burst with error filter)."""
import warnings

import pytest


def test_canary_success_shim_bursts():
    """If someone reintroduces net_res.success in production, suite must warn."""
    from netmedic.canary_shim_prod import read_success_shim

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", UserWarning)
        read_success_shim()
        assert any(issubclass(x.category, UserWarning) for x in w), "Expected UserWarning for NetResult.success"
        assert any("NetResult.success is deprecated" in str(x.message) for x in w)
    # Note: with filterwarnings = error:NetResult.*:UserWarning (last line prevails) this would be
    # pytest.raises(UserWarning) — canary lives in prod namespace so immediate caller not in tests → would burst.


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
