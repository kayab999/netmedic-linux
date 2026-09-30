# Repository Settings Checklist (M10)

Guards code cannot express. Verify by hand after releases that touch
process or supply chain. Items marked [x] are confirmed active.

## Branch protection

- [x] `main` merges via PR only (`--no-ff`, feature branches preserved).
- [x] CI must pass (12 checks: sast, test x6, netns-golden, smoke,
  build-smoke, container-build).
- [ ] Required reviews before merge (single-maintainer self-merge today).
  Settings → Branches → Require a pull request before merging.

## Tag protection

- [x] Ruleset "Protect version tags" — `v*` deletion and
  non-fast-forward updates blocked (created for v1.6.1).
- [x] Release workflow publishes from tags only (`on.push.tags: v*`).

## Supply chain (M6)

- [x] All workflow actions pinned by SHA (`test_no_floating_action_refs`).
- [x] `requirements.lock` hash-pinned; binary builds use `--require-hashes`.
- [x] Release `build` job is read-only; `publish` holds the write token
  behind the `release` environment.
- [x] SLSA provenance attestation on shipped artifacts.
- [x] `pip-audit` blocking against the lock in CI.
- [x] Dependabot pip entries point at `/netmedic`, `/netmedic_ai`.
- [ ] GPG long-lived key: migrate verifiers to provenance, then remove key.
- [ ] Commit/tag signing: enable vigilant mode + required signatures.

## Hygiene

- [x] No vendored binaries in git (`dist/`, `build/`, `*.so` ignored).
- [x] `git gc` discipline: run after merges/tags; alert above 50 MB loose.
- [x] Strict-typing map (`mypy.ini`) has no glob sections
  (`test_m9_typing.py` bans the pattern that once voided all checks).

## Verification commands

```bash
git push origin :refs/tags/v1.8.0        # expect: rejected (protected)
grep -rhoE "uses: [^ ]+" .github/workflows/ | grep -v "@[0-9a-f]\{40\}"
# expect: no output (all pinned)
grep -c "^ *--hash=sha256:" requirements.lock  # expect: 6
git count-objects -v                         # size-pack vs size
```
