# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.10.x  | Yes |
| 1.9.x   | No — superseded by 1.10.x (upgrade to 1.10.x) |
| 1.8.x   | No — superseded by 1.9.x (upgrade to 1.9.x) |
| 1.6.x   | No — affected by SECURITY_ADVISORY_v1.6.1.md (upgrade to 1.9.x) |
| 1.5.x   | No (upgrade to 1.9.x) |
| < 1.5   | No |

**Support policy:** only the latest minor line receives security fixes. 1.8.x is
retired as of 1.9.0; the upgrade requires reinstalling the helper and polkit
policy because `HELPER_VERSION` changed. This is a deliberate single-maintainer
decision, not an accidental omission.

## Release signatures

Release artifacts are signed with the dedicated Kayab Software release key.
It is sign-only and is never used for Git commits or everyday email.

- **Fingerprint:** `8C1BA036E834F3235593561C1A83A6D7885575E6`
- **Public key:** [docs/RELEASE_KEY.asc](docs/RELEASE_KEY.asc)
- **UID:** `Kayab Software Release Signing <support@kayabsoftware.com>`
- **Algorithm:** RSA 4096, created 2026-11-19, expires 2028-11-18.

Verify a downloaded release:

```bash
gpg --import docs/RELEASE_KEY.asc
gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum -c SHA256SUMS
```

`gpg --verify` must report a good signature made by the fingerprint above.
Importing the key without a trust path still prints `Good signature` together
with an untrusted-key warning; compare the fingerprint that GPG prints instead
of relying on the warning text. `sha256sum -c` must report `OK` for every
artifact listed in `SHA256SUMS`.

## Threat model

NetMedic is a **single-user desktop** privileged network tool. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

Primary residual risk: a **same-UID** local process can talk to the IPC socket and may trigger polkit prompts; authorization still depends on the user (or `auth_admin_keep`).

## Hardening checklist (operators)

1. Install the system helper + polkit policy:
   ```bash
   ./scripts/install-polkit-policy.sh
   netmedic --status
   ```
2. Confirm `core_ready: true`, `privileged_ready: true` and helper path `/usr/libexec/netmedic/helper` (`production_ready` is a deprecated alias of `core_ready`).
3. Do **not** set `NETMEDIC_ALLOW_LEGACY_ELEVATION=1` in production.
4. Do **not** set `NETMEDIC_SKIP_POLKIT=1` outside tests (`NETMEDIC_TEST_MODE=1` only).
5. Keep state dir private (`~/.local/state/netmedic` mode `0700`).
6. MCP mutating tools: leave `NETMEDIC_MCP_ALLOW_MUTATING` unset unless intentional.

## Reporting a vulnerability

Email **support@kayabsoftware.com** (or open a private security advisory on GitHub if available).

Please include:

- NetMedic version (`netmedic --status`)
- Distro and desktop environment
- Steps to reproduce
- Impact assessment (privilege, data exposure, DoS)

We aim to acknowledge within 7 days and ship fixes for supported versions as soon as practical.

Coordinated disclosure timeline: 90 days from acknowledgement, or earlier by mutual agreement. We credit reporters in release notes unless they prefer anonymity.

## Disclosure

We prefer coordinated disclosure. Public issues for non-sensitive bugs are fine; do not post exploit details for elevation bypasses until a fix is released.
