# AI supply chain (Fase 7)

`netmedic_ai` is **out of the release supply chain** until the lock below lands.

- Dependency: `llama-cpp-python>=0.2.57` (sdist only on PyPI; no wheel).
- Install must use `pip install --require-hashes -r netmedic_ai/requirements.lock`.
- Generate the lock with `scripts/generate_ai_lock.sh` (pip-compile --generate-hashes)
  in CI on linux x86_64 / cp312; commit the result. Do not hand-edit.
- Build deps of the sdist (scikit-build-core, cmake, ninja, ...) need hashes too.
- The model GGUF SHA256 is hardcoded in `netmedic_ai/pilot.py` (`MODEL_SHA256`)
  and verified at load; the `.sum` sidecar is no longer trusted.
- Runtime has no hash guard (a same-UID process can edit both files). Verification
  is install-time (`--require-hashes`) + CI (`pip-audit`).
- If the lock cannot be produced in a PR, keep AI declared out-of-chain here.
