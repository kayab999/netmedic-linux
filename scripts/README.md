# Build Scripts

| Script | Purpose |
|--------|---------|
| `build_binary.sh` | Full PyInstaller build via `netmedic.spec` |
| `build_standalone.sh` | Minimal one-file binary (no AI module) |
| `package_appimage.sh` | Create AppImage from standalone build |
| `generate_icon.py` | Regenerate `assets/netmedic.png` |

All scripts resolve paths relative to the repository root automatically.

```bash
./scripts/build_binary.sh
./scripts/package_appimage.sh
python scripts/generate_icon.py
```