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

### Manual setup (Python 3.10–3.12; see `requirements.lock`)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.lock
pip install -e netmedic/ --config-settings editable_mode=strict
pip install -e netmedic_ai/
```

## Running the Application

```bash
# GUI
./venv/bin/netmedic

# Headless (IPC daemon only — no GTK import)
./venv/bin/netmedic --headless
```

## Testing (438 tests, 57 files; CI gate `--cov-fail-under=75`, currently 83%)

```bash
./venv/bin/python -m pytest tests/ -v
```

Test categories (see `tests/` — 57 files):
- IPC + auth: `test_ipc*.py`, `test_polkit_*.py`, `test_action_catalog.py`, `test_audit_log.py`, `test_security.py`
- Helper verbs + contracts: `test_helper_verbs.py`, `test_command_runner_allowlist.py`, `test_policy_and_catalog_contract.py`, `test_verbs_doc.py`
- Operators + diagnostics: `test_operators.py`, `test_angristan_operator.py`, `test_network*.py`, `test_probes.py`, `test_sensors*.py`
- UI (headless-safe, no `show_all`): `test_ui_elements_wiring.py`, `test_ui_flows.py`, `test_ui_vpn_panel.py`, `test_ai_console_overlay.py`
- Lifecycle + runtime: `test_lifecycle.py`, `test_runtime*.py`, `test_signal_cleanup.py`, `test_resilience.py`
- Properties (Hypothesis): `test_properties.py` — framing, tokens, catalog, verb totality, redaction
- Golden replay (root, `-m netns`): `test_golden_replay_ns.py` via `scripts/netns-golden.sh`
- Mutation scope (`setup.cfg`): `ipc_security.py` + `helper_verbs.py`, 94% kill rate

## Linting & types

```bash
./venv/bin/ruff check netmedic/ netmedic_ai/ tools/ tests/
./venv/bin/mypy --config-file mypy.ini netmedic/netmedic/ipc_security.py netmedic/netmedic/helper_verbs.py netmedic/netmedic/action_catalog.py netmedic/netmedic/models.py netmedic/netmedic/ipc_bridge.py netmedic/netmedic/ipc_actions.py netmedic/netmedic/runtime.py netmedic/netmedic/lifecycle.py netmedic/netmedic/config.py netmedic/netmedic/polkit_auth.py
```

ruff selects `E,F,B,S` (see `ruff.toml` for documented test/sim exceptions).
mypy is strict on 10 modules; the dependency-graph cascade is silenced via
`netmedic.* ignore_errors` (most-specific match keeps strict files strict).

## Building Binaries

```bash
./scripts/build_binary.sh       # PyInstaller via netmedic.spec
./scripts/build_standalone.sh   # Minimal one-file build
./scripts/package_appimage.sh   # AppImage packaging
```

Requires PyInstaller and system GTK libraries. For byte-identical builds,
use the pinned container: `docker build -f Dockerfile.build -t netmedic-build .`
(see `Dockerfile.build` header for the apt-vs-pip split rationale).

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