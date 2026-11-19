# Repository Settings Checklist (owner)

Settings the code cannot enforce. The owner must configure and verify them in
GitHub; do not mark an item complete without evidence from the repository
settings page (screenshot, API output or audit-log entry). No PGP key or
fingerprint is invented here: the owner must publish the real one.

## Branch protection — `main`

- [x] **PR-only merges.** Require a pull request before merging; block direct
  pushes and force-pushes to `main`.
- [x] **Required CI.** Require the repository's required status checks (CI and
  CodeQL) to pass before merge. Confirm the exact check names in
  `.github/workflows/ci.yml` and the branch-protection page.
- [x] **Required review.** Require at least one approving review before merge.
  A single-maintainer repository cannot satisfy this with self-approval; the
  owner must decide whether to add a reviewer or document the exception.

**Evidence (2026-11-19, `gh api repos/kayab999/netmedic-linux/branches/main/protection`):**
`strict=true`; `enforce_admins=false`; `required_approving_review_count=1`;
`dismiss_stale_reviews=true`; `required_conversation_resolution=true`;
`required_linear_history=true`; `allow_force_pushes=false`;
`allow_deletions=false`. Required contexts:
`sast`, `test (0, 3.10)`–`test (0, 3.13)`, `test (1, 3.10)`–`test (1, 3.13)`,
`helper-install-integration`, `netns-golden`, `smoke`, `build-smoke`,
`container-build`. **Documented exception:** with one maintainer, the required
review cannot be satisfied by self-approval, so merges use the owner's
administrative bypass after the full check set is green. Every such merge is
recorded in the PR timeline.

## Tag ruleset — `v*`

- [x] **Protect version tags.** Create/verify a ruleset targeting `v*` that
  blocks tag deletion and non-fast-forward updates.
- [x] **Restrict tag creation.** Limit who can create matching tags to the
  release owner.
- [x] **Tag-driven release only.** Confirm the release workflow still triggers
  only from `v*` tag pushes.

**Evidence (2026-11-19):** ruleset `24150308` ("Protect version tags",
`target=tag`, `enforcement=active`, `refs/tags/v*`) applies `creation`,
`deletion` and `non_fast_forward`. Its only bypass actor is user `kayab999`
(`id 252370331`) with `bypass_mode=always`, so other actors cannot create
matching tags. `.github/workflows/release.yml` still has a single trigger:
`push.tags: ["v*"]`.

## Release signing (PGP)

- [x] **Long-lived release key.** Keep the private key offline/off-repo; publish
  the public key and its **full 40-hex fingerprint** in `SECURITY.md` next to
  the release verification instructions. A short key id is not sufficient.
- [x] **Signed release assets.** Publish `SHA256SUMS` plus its detached
  signature (`SHA256SUMS.asc`); verify the signature in the release workflow
  with the published fingerprint.
- [x] **Signed tags/commits (decision).** If required, enable GitHub vigilant
  mode and required commit/tag signatures; otherwise document that provenance
  attestations are the verification path.

**Evidence (2026-11-19):** dedicated RSA-4096 sign-only key
`8C1BA036E834F3235593561C1A83A6D7885575E6`
(`Kayab Software Release Signing <support@kayabsoftware.com>`, valid until
2028-11-18). Public key committed at `docs/RELEASE_KEY.asc`; fingerprint and
verification commands in `SECURITY.md`; a doc-truthfulness test recomputes the
OpenPGP v4 fingerprint from the committed key. `RELEASE_GPG_PRIVATE_KEY` and
`RELEASE_GPG_KEY_ID` exist **only** as secrets of the protected `release`
environment (`id 22990919764`), which requires owner approval and accepts only
tag deployments matching `v*`. The `build` job stays `contents: read`; the
`publish` job imports the key and fails closed when the secrets are absent.
**Decision:** commit/tag signing and GitHub vigilant mode are not enabled.
Verification relies on the published fingerprint plus the `SHA256SUMS.asc`
signature and the SLSA build provenance attestation.

## Supply chain (verify, code-enforced)

- [x] Workflow actions pinned by full SHA
  (`test_no_floating_action_refs`).
- [x] `requirements.lock` hash-pinned; binary builds use `--require-hashes`.
- [x] Release `build` job read-only; `publish` uses the protected `release`
  environment.
- [x] `pip-audit` blocking against the lock in CI.
- [x] Dependabot pip entries point at `/netmedic` and `/netmedic_ai`.
- [x] No vendored binaries in git (`dist/`, `build/`, `*.so` ignored).

**Evidence (2026-11-19):** the floating-action grep returns no lines;
`requirements.lock` has 6 hash-pinned entries; `pip-audit` runs in the `sast`
job and in the scheduled `supply-chain-audit` job; `.github/dependabot.yml`
targets `/netmedic`, `/netmedic_ai` and GitHub Actions; `git ls-files` has no
tracked `dist/`, `build/`, `.so` or `.bin` artifacts. GitHub vulnerability
alerts and Dependabot automated security fixes are enabled
(`automated-security-fixes: {"enabled":true}`).

## Verification commands

```bash
# Tag ruleset: expect enforcement=active, the three rules and only the owner
# in bypass_actors. Do not test by deleting a real tag: the owner can bypass.
gh api repos/kayab999/netmedic-linux/rulesets/24150308 \
  --jq '{enforcement, rules: [.rules[].type], bypass: [.bypass_actors[].actor_id]}'

# All actions pinned: expect no output
grep -rhoE "uses: [^ ]+" .github/workflows/ | grep -v "@[0-9a-f]\{40\}"

# Lock hashes: expect 6
grep -c "^ *--hash=sha256:" requirements.lock

# Repository size
git count-objects -v
```
