# Repository Settings Checklist (owner)

Settings the code cannot enforce. The owner must configure and verify them in
GitHub; do not mark an item complete without evidence from the repository
settings page (screenshot, API output or audit-log entry). No PGP key or
fingerprint is invented here: the owner must publish the real one.

## Branch protection — `main`

- [ ] **PR-only merges.** Require a pull request before merging; block direct
  pushes and force-pushes to `main`.
- [ ] **Required CI.** Require the repository's required status checks (CI and
  CodeQL) to pass before merge. Confirm the exact check names in
  `.github/workflows/ci.yml` and the branch-protection page.
- [ ] **Required review.** Require at least one approving review before merge.
  A single-maintainer repository cannot satisfy this with self-approval; the
  owner must decide whether to add a reviewer or document the exception.

## Tag ruleset — `v*`

- [ ] **Protect version tags.** Create/verify a ruleset targeting `v*` that
  blocks tag deletion and non-fast-forward updates.
- [ ] **Restrict tag creation.** Limit who can create matching tags to the
  release owner.
- [ ] **Tag-driven release only.** Confirm the release workflow still triggers
  only from `v*` tag pushes.

## Release signing (PGP)

- [ ] **Long-lived release key.** Keep the private key offline/off-repo; publish
  the public key and its **full 40-hex fingerprint** in `SECURITY.md` next to
  the release verification instructions. A short key id is not sufficient.
- [ ] **Signed release assets.** Publish `SHA256SUMS` plus its detached
  signature (`SHA256SUMS.asc`); verify the signature in the release workflow
  with the published fingerprint.
- [ ] **Signed tags/commits (decision).** If required, enable GitHub vigilant
  mode and required commit/tag signatures; otherwise document that provenance
  attestations are the verification path.

## Supply chain (verify, code-enforced)

- [ ] Workflow actions pinned by full SHA
  (`test_no_floating_action_refs`).
- [ ] `requirements.lock` hash-pinned; binary builds use `--require-hashes`.
- [ ] Release `build` job read-only; `publish` uses the protected `release`
  environment.
- [ ] `pip-audit` blocking against the lock in CI.
- [ ] Dependabot pip entries point at `/netmedic` and `/netmedic_ai`.
- [ ] No vendored binaries in git (`dist/`, `build/`, `*.so` ignored).

## Verification commands

```bash
# Tag protection: expect "rejected" (run only after the tag exists)
git push origin :refs/tags/v1.9.0

# All actions pinned: expect no output
grep -rhoE "uses: [^ ]+" .github/workflows/ | grep -v "@[0-9a-f]\{40\}"

# Lock hashes: expect 6
grep -c "^ *--hash=sha256:" requirements.lock

# Repository size
git count-objects -v
```
