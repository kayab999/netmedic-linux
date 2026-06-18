# Contributing to NetMedic Linux

Thank you for your interest in contributing. NetMedic is built on principles of **technical sovereignty**, **integrity**, and **resilience**.

## Getting Started

1. Fork the repository and clone locally.
2. Run `./install.sh` to set up the development environment.
3. Create a feature branch: `git checkout -b feature/your-feature`.
4. Make changes and ensure tests pass:
   ```bash
   PYTHONPATH="netmedic:." venv/bin/python -m pytest tests/ -v
   venv/bin/ruff check netmedic/ netmedic_ai/ tests/
   ```
5. Submit a pull request with a clear description of changes.

## Code Standards

- **Architecture:** New network features should follow the operator pattern (`netmedic/operators/`).
- **Security:** Never log secrets in plain text. Pin third-party script hashes.
- **IPC:** Privileged actions must go through `ipc_security.IPCSession` validation.
- **Tests:** All new functionality requires unit or integration test coverage.
- **Style:** Match existing code conventions. Run `ruff check` before submitting.

## Pull Request Checklist

- [ ] Tests pass (`pytest tests/`)
- [ ] No new linter errors (`ruff check`)
- [ ] Documentation updated if behavior or APIs changed
- [ ] CHANGELOG.md updated for user-facing changes

## Reporting Issues

Include:
- Linux distribution and version
- Python version
- Steps to reproduce
- Relevant log excerpts from `~/.local/state/netmedic/netmedic.log` (redact secrets)

## Architecture Decisions

Significant changes should align with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). For large features, open an issue for discussion before implementation.

---

*NetMedic is a foundation for network freedom on Linux.*