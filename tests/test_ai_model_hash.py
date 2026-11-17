"""Guardian: model GGUF hash must be hardcoded and match the legacy .sum."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_model_sha256_hardcoded_and_matches_sum() -> None:
    sum_path = ROOT / "nandi-mini-tool-calling.sum"
    if not sum_path.exists():
        # Model not shipped in this checkout; skip gracefully.
        import pytest

        pytest.skip("model .sum not present in this checkout")
    expected = sum_path.read_text(encoding="utf-8").strip()
    # Import without triggering llama_cpp (optional).
    import importlib.util

    spec = importlib.util.spec_from_file_location("pilot", ROOT / "netmedic_ai" / "pilot.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Avoid executing _resolve_asset_dir side effects that need the model.
    spec.loader.exec_module(mod)
    assert mod.MODEL_SHA256 == expected
