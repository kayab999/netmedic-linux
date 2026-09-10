# Development Guide

## Repository Layout

| Path | Purpose |
|------|---------|
| `netmedic/netmedic/` | Core application source |
| `netmedic_ai/` | Optional AI pilot (llama-cpp-python) |
| `tests/` | Pytest suite |
| `scripts/` | Build and packaging automation |
| `assets/` | Icon and `.desktop` template |
| `tools/` | Optional integrations (MCP server) |

## Environment Setup

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
./install.sh
```

The installer creates `venv/`, installs `netmedic` in **strict** editable mode (`editable_mode=strict`), and optionally installs the AI module.

After adding a new `netmedic/*.py` module, re-run the same `pip install -e` command so the snapshot used by `venv/bin/netmedic` (dock / `.desktop` Exec) includes it. Editing an existing file does not need a reinstall (snapshot entries are symlinks).

### Manual setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e netmedic/ --config-settings editable_mode=strict
pip install pytest ruff PyGObject
```

## Running the Application

```bash
# GUI
./venv/bin/netmedic

# Headless (IPC daemon only — no GTK import)
./venv/bin/netmedic --headless
```

## Testing

```bash
./venv/bin/python -m pytest tests/ -v
```

Test categories:
- `test_system.py` — CommandRunner, pkexec, timeouts
- `test_security.py` — Log redaction, SHA256 integrity
- `test_ipc.py` — IPC dispatcher and authorization
- `test_resilience.py` — Crash recovery with isolated state
- `test_ai_package.py` — AI registry and guardrail

## Linting

```bash
./venv/bin/ruff check netmedic/ netmedic_ai/ tests/
```

## Building Binaries

```bash
./scripts/build_binary.sh       # PyInstaller via netmedic.spec
./scripts/build_standalone.sh   # Minimal one-file build
./scripts/package_appimage.sh   # AppImage packaging
```

Requires PyInstaller and system GTK libraries.

## AI Module Setup

The AI pilot requires:

1. `pip install -e "netmedic_ai[runtime]"` and `pip install -e "netmedic[ai]"`
2. Download or place the GGUF model at repo root:
   - `nandi-mini-tool-calling.gguf`
   - `nandi-mini-tool-calling.sum` (SHA256 checksum)

Model files are **not** committed to git (see `.gitignore`).

Generate checksum after downloading:
```bash
sha256sum nandi-mini-tool-calling.gguf | awk '{print $1}' > nandi-mini-tool-calling.sum
```

## Optional MCP Integration

```bash
pip install fastmcp
python tools/netmedic_mcp.py
```

## State & Logs

Runtime files (XDG-compliant):
- State: `~/.local/state/netmedic/`
- Data: `~/.local/share/netmedic/`
- Log: `~/.local/state/netmedic/netmedic.log` (mode 600)