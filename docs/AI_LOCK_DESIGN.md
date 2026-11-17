# Fase 6 — Design note: AI dependency lock with hashes (no code yet)

Problem: `netmedic_ai` depends on `llama-cpp-python>=0.2.57` with no hash pin;
supply-chain audit cannot attest it. AI console imports it lazily.

Proposal:
- Add `netmedic_ai/requirements.lock` with `--require-hashes` (pip-compile).
- Install only via `pip install --require-hashes -r requirements.lock`.
- Runtime guard: `ai_console.py` checks `AI_LOCK_SHA256` before import; on
  mismatch disable the console + warn (fail-closed, no crash).
- Scope: optional `ai` extra only; base `netmedic` keeps zero third-party deps.
  No helper, policy, or IPC changes.

Open questions (approval needed before coding):
1. One platform lock (linux x86_64) or per-arch matrix?
2. Vendor the wheel (~30 MB) or fetch with hash verification?
3. Guard in `ai_console.py` or new `netmedic/ai_lock.py`?

STOP: awaiting approval before any code change.
