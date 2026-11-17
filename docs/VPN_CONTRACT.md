# VPN contract — NetMedic vs. vendored installer (Fase 2b)

The vendored installer is `netmedic/netmedic/data/vpn/openvpn-install.sh`
(commit `9c966d4d043a0340503d6df577aa174a68468aed`, SHA256
`e0ac8731423204c671f7699003e9fb6f191be77ae15ca8e5a28031f498947a07`).
NetMedic must speak its **non-interactive CLI**, not the legacy env/menu
interface. This document is the single source of truth for that mapping.

## Literal `--help` output (captured 2026-11-17, without root)

### `bash openvpn-install.sh --help`

```
OpenVPN installer and manager

Usage: openvpn-install <command> [options]

Commands:
install       Install and configure OpenVPN server
uninstall     Remove OpenVPN server
client        Manage client certificates
server        Server management
interactive   Launch interactive menu

Global Options:
--verbose     Show detailed output
--log <path>  Log file path (default: openvpn-install.log)
--no-log      Disable file logging
--no-color    Disable colored output
-h, --help    Show help

Run 'openvpn-install <command> --help' for command-specific help.
```

### `bash openvpn-install.sh install --help`

```
Install and configure OpenVPN server

Usage: openvpn-install install [options]

Options:
-i, --interactive     Run interactive install wizard

Network Options:
--endpoint <host>     Public IP or hostname for clients (auto-detected)
--endpoint-type <4|6> Endpoint IP version: 4 or 6 (default: 4)
--ip <addr>           Server listening IP (auto-detected)
--client-ipv4         Enable IPv4 for VPN clients (default: enabled)
--no-client-ipv4      Disable IPv4 for VPN clients
--client-ipv6         Enable IPv6 for VPN clients
--no-client-ipv6      Disable IPv6 for VPN clients (default)
--subnet-ipv4 <x.x.x.0>  IPv4 VPN subnet (default: 10.8.0.0)
--subnet-ipv6 <prefix>   IPv6 VPN subnet (default: fd42:42:42:42::)
--port <num>          OpenVPN port (default: 1194)
--port-random         Use random port (49152-65535)
--protocol <proto>    Protocol: udp or tcp (default: udp)
--mtu <size>          Tunnel MTU (default: 1500)

DNS Options:
--dns <provider>      DNS provider (default: cloudflare)
Providers: system, unbound, cloudflare, quad9, quad9-uncensored,
fdn, dnswatch, opendns, google, yandex, adguard, nextdns, custom
--dns-primary <ip>    Custom primary DNS (requires --dns custom)
--dns-secondary <ip>  Custom secondary DNS (optional)

Security Options:
--cipher <cipher>     Data channel cipher (default: AES-128-GCM)
Ciphers: AES-128-GCM, AES-192-GCM, AES-256-GCM, AES-128-CBC,
AES-192-CBC, AES-256-CBC, CHACHA20-POLY1305
--cert-type <type>    Certificate type: ecdsa or rsa (default: ecdsa)
--cert-curve <curve>  ECDSA curve (default: prime256v1)
Curves: prime256v1, secp384r1, secp521r1
--rsa-bits <size>     RSA key size: 2048, 3072, 4096 (default: 2048)
--cc-cipher <cipher>  Control channel cipher (auto-selected)
--tls-version-min <ver>  Minimum TLS version: 1.2 or 1.3 (default: 1.2)
--tls-ciphersuites <list>  TLS 1.3 cipher suites, colon-separated
--tls-groups <list>   Key exchange groups, colon-separated
(default: X25519:prime256v1:secp384r1:secp521r1)
--hmac <alg>          HMAC algorithm: SHA256, SHA384, SHA512 (default: SHA256)
--tls-sig <mode>      TLS mode: crypt-v2, crypt, auth (default: crypt-v2)
--auth-mode <mode>    Auth mode: pki, fingerprint (default: pki)
fingerprint requires OpenVPN 2.6+
--server-cert-days <n>  Server cert validity in days (default: 3650)

Other Options:
--multi-client        Allow same cert on multiple devices

Initial Client Options:
--client <name>       Initial client name (default: client)
--client-password [p] Password-protect client (prompts if no value given)
--client-cert-days <n>  Client cert validity in days (default: 3650)
--no-client           Skip initial client creation

Examples:
openvpn-install install
openvpn-install install --port 443 --protocol tcp
openvpn-install install --dns quad9 --cipher AES-256-GCM
openvpn-install install -i
```

### `bash openvpn-install.sh client --help`

```
Manage client certificates

Usage: openvpn-install client <subcommand> [options]

Subcommands:
add <name>     Add a new client
list           List all clients
revoke <name>  Revoke a client certificate
renew <name>   Renew a client certificate

Run 'openvpn-install client <subcommand> --help' for more info.
```

### `bash openvpn-install.sh client add --help`

```
Add a new VPN client

Usage: openvpn-install client add <name> [options]

Options:
--password [pass]   Password-protect client (prompts if no value given)
--cert-days <n>     Certificate validity in days (default: 3650)
--output <path>     Output path for .ovpn file (default: ~/<name>.ovpn)

Examples:
openvpn-install client add alice
openvpn-install client add bob --password
openvpn-install client add charlie --cert-days 365 --output /tmp/charlie.ovpn
```

### `bash openvpn-install.sh client revoke --help`

```
Revoke a client certificate

Usage: openvpn-install client revoke <name> [options]

Options:
-f, --force   Skip confirmation prompt

Examples:
openvpn-install client revoke alice
openvpn-install client revoke bob --force
```

## Mapping table (NetMedic → upstream)

| NetMedic input | Upstream flag / variable | Script line (evidence) | Valid values |
|---|---|---|---|
| `DNS=3` (Cloudflare) | `--dns cloudflare` | `parse_dns_provider` case (line 424-433); `validate_configuration` DNS case (line 646-648) | provider *name*, not number: `system, unbound, cloudflare, quad9, quad9-uncensored, fdn, dnswatch, opendns, google, yandex, adguard, nextdns, custom` |
| `PORT_CHOICE=1` (UDP 1194) | `--port 1194` + `--protocol udp` | `--port <num>` / `--protocol <proto>` (install help); interactive `PORT_CHOICE` (line 2288-2295) and `PROTOCOL_CHOICE` (line 2311-2316) are **not** honoured non-interactively | port 1-65535; protocol `udp`/`tcp` |
| `PROTOCOL_CHOICE=1` (UDP) | `--protocol udp` | install help `--protocol <proto>`; `PROTOCOL` case `udp \| tcp` (line 640-642) | `udp`, `tcp` |
| `IPV6_SUPPORT=n` | `--no-client-ipv6` (default) | `--client-ipv6` / `--no-client-ipv6` (install help); `IPV6_SUPPORT` (line 2074) is an internal alias for `CLIENT_IPV6`, ignored by the CLI | flag presence/absence |
| `COMPRESSION_ENABLED=n` | (none) | Compression was removed upstream; no flag exists | n/a — drop |
| `MENU_OPTION=1` (add client) | `client add <name>` | `manageMenu` case `1)` → `newClient` (line 4516-4518); menu item "1) Add a new user" (line 4506) | subcommand, not env |
| `MENU_OPTION=2` (list) | `client list` | `manageMenu` case `2)` → `listClients` (line 4519-4520); menu item "2) List client certificates" (line 4507) | subcommand |
| `MENU_OPTION=2` for **revoke** (bug) | `client revoke <name> --force` | `manageMenu` case `3)` → `revokeClient` (line 4521-4522); menu item "3) Revoke existing user" (line 4508). NetMedic's `MENU_OPTION=2` only **lists** clients — revocation never happens | subcommand + `--force` |
| `CLIENT=<name>` | positional `<name>` to `client add`/`client revoke` | `client add <name>` / `client revoke <name>` (help) | `validate_client_name` charset (a-z, 0-9, `_`, `-`) |
| `PASS=1` (no password) | omit `--password` | `--password [pass]` (client add help) | omit or `--password <value>` |
| (new, F4) client `.ovpn` | `client add <name> --output <path>` | `--output <path>` (client add help) | absolute path under `/run/netmedic` |
| revoke confirmation | `--force` / `-f` | `client revoke --help` | always pass `--force` (no interactive prompt) |

## Consequences for Fase 3

- `VPN_ALLOWED_ENV_KEYS` and `_validate_vpn_script_env` are removed; no caller env dict crosses IPC.
- Three typed verbs: `vpn-install`, `vpn-add-client`, `vpn-revoke-client`, each with its own `exec.argv1`.
- Helper builds `/bin/bash <staged> <subcommand> <flags>` with validated parameters.
- `vpn-install` defaults: `--port 1194 --protocol udp --dns cloudflare --no-client-ipv6 --client client`.
- `validate_client_name` stays (charset). Port 1-65535, protocol `udp`/`tcp`, dns in the closed enum above.
- `vpn-revoke-client` always passes `--force`; `uninstall` and `renew` are **not** exposed.
