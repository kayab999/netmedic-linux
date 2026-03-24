# Changelog - NetMedic Linux

## [1.0.0-rc1] - 2026-03-03
### Added
- **Security Hardening**: SHA256 integrity verification for external operator scripts (e.g., OpenVPN installer).
- **Log Redaction**: Automatic redaction of sensitive arguments (passwords, tokens, keys) in execution logs.
- **Robust Cleanup**: Global singleton for Network Management and system signal handlers (SIGINT, SIGTERM) ensure virtual interfaces are removed on exit.
- **Configurable Timeouts**: Support for short (30s) and long (300s) command timeouts via global configuration.

### Fixed
- **pkexec UX**: Friendly error dialogs and UI recovery when user cancels authentication (Exit codes 126/127).
- **Interface Leak**: Fixed zombie 'medicXX' interfaces when the app was closed abruptly.
- **VPNPanel Decoupling**: Modularized UI components to allow headless/detached execution.

## [1.0.0-alpha] - 2026-01-10
- Initial prototype for Debian, Fedora and Arch Linux.
- Basic network diagnostics and repair tools.
- Experimental VPN and WiFi operators.
