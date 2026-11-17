# Vendored installer provenance

`openvpn-install.sh` is vendored verbatim from the upstream
[angristan/openvpn-install](https://github.com/angristan/openvpn-install)
repository. NetMedic never downloads it at runtime.

| Field | Value |
|---|---|
| Upstream repository | `https://github.com/angristan/openvpn-install` |
| Commit | `9c966d4d043a0340503d6df577aa174a68468aed` |
| Commit date | `2025-12-31 11:20:30 +0100` |
| Upstream path | `openvpn-install.sh` |
| Lines | 4546 |
| SHA256 | `e0ac8731423204c671f7699003e9fb6f191be77ae15ca8e5a28031f498947a07` |
| License | MIT (see `LICENSE.openvpn-install`) |

The SHA256 above is the **single** trust anchor. It is stored as
`netmedic.helper_verbs.PINNED_VPN_INSTALL_SHA256`; the root helper verifies
the file it reads against that constant before executing it. A guardian test
recomputes the hash of this file, so an accidental edit fails CI.

## Installation target

`scripts/install-polkit-policy.sh` and the Debian packaging rules install
these bytes as:

```
/usr/lib/netmedic/scripts/openvpn-install.sh   root:root 0644
```

The helper resolves `script_id = "openvpn-install"` to that fixed path. It
never accepts a caller-supplied path or hash.

## Re-pinning

See `docs/VPN_REPIN.md`. Do not edit the script by hand: replace it with the
exact upstream bytes, update the SHA256 in `helper_verbs.py`, update this
file, and let the tests prove the three values agree.
