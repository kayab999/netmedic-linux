# Build Scripts

| Script | Purpose |
|--------|---------|
| `build_binary.sh` | Full PyInstaller build via `netmedic.spec` |
| `build_standalone.sh` | Minimal one-file binary (no AI module) |
| `package_appimage.sh` | Create AppImage from standalone build |
| `generate_icon.py` | Regenerate `assets/netmedic.png` |
| `check-deps.sh` | Runtime preflight (bins + Python 3.10–3.12; CI runs first) |
| `install-polkit-policy.sh` | Install system helper + polkit policy (`/usr/libexec/netmedic/helper`) |
| `netns-golden.sh` | Hermetic netns harness (A WAN-drop + B TCP-block), CI `netns-golden` job |
| `prepare_release_assets.sh` | Binary + `SHA256SUMS` + SBOMs (freeze + CycloneDX) for releases |
| `smoke_release.sh` | 6-step release smoke (version, status, helper, policy, pytest) |
| `runbook_vm_evidence.py` | GUI runbook evidence helper (renew/flush rows) |
| `soak_sample.sh` | Hourly soak sampler → `soak.csv` (RSS/FDs/threads/log sizes); see `docs/OPS.md` |

All scripts resolve paths relative to the repository root automatically.

```bash
./scripts/build_binary.sh
./scripts/package_appimage.sh
python scripts/generate_icon.py
```