# AI supply chain (Fase 7)

## Status in 1.9.0

`netmedic_ai` is **experimental and outside the supported 1.9.0 surface**. It
is **out of the release supply chain** until the lock below lands, and the main
release does not depend on it. The GUI/CLI, IPC, helper and Polkit path remain
fully functional without AI.

Strict or shared deployments that enable the AI pilot must point
`NETMEDIC_AI_MODEL_DIR` at a model file and directory that are **admin-owned
and not writable by the user running NetMedic** (read-only mount or root-owned
`0755` directory with a `0644` model). This limits the verify-then-reopen race
in `netmedic_ai/pilot.py` until issue #62-B loads from the verified descriptor.

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
