# D-Bus Privileged Service — v2.0 Design (design track, not a release)

Status: **design + non-installed prototype**. Nothing in this track is
shipped by the installer, and the `pkexec` helper remains the default
through v1.x. Do not merge this branch to a release line.

## 1. Goals and non-goals

**Goals.** Retire two vulnerability classes, not instances:

- **F3 (interpreter hijacking) as a class.** Today root executes
  `/usr/libexec/netmedic/helper`, a shell wrapper around a Python
  interpreter path. A D-Bus service runs as a root-owned systemd unit
  with a fixed `/usr/bin/python3 -I -s` command line owned by root —
  there is no wrapper for an installer (or attacker) to point at a
  venv interpreter, because there is no interpreter *choice* at all.
- **F4 (polkit granularity spoofing) as a class.** Today `pkexec`
  disambiguates verbs via `argv[1]`, which the *caller supplies*.
  On the bus, the service learns the caller from the bus daemon
  (unique name → PID → UID, optionally systemd unit) and authorizes
  that attested subject explicitly. There is no caller-controlled
  string in the authorization decision.

**Non-goals.**

- Replacing the Unix-socket IPC (`ipc_bridge.py`) or the daemon's
  dispatch gates (peer UID, token, `confirmed`, audit intent). The
  D-Bus service sits *behind* the same daemon; defense in depth stays.
- Multi-user or remote use (still out of scope per `THREAT_MODEL.md`).
- Changing verb semantics: `plan_verb`, `validators`,
  `action_catalog.ACTIONS`, staging, `killpg` deadlines and journal
  records are reused verbatim.

## 2. Architecture

- **Bus and name.** System bus, well-known name `com.kayab.netmedic`,
  object `/com/kayab/netmedic/Helper`, interface
  `com.kayab.netmedic.Helper1` with a single method:
  `Execute(sa{ss} verb, args_json) → (b ok, s message, s details)`.
- **Service process.** Systemd unit `netmedic-helper.service`,
  `Type=dbus`, `BusName=com.kayab.netmedic`, `ExecStart=/usr/bin/python3
  -I -s /usr/lib/netmedic/helper_service.py`, `User=root`. Code lives
  root-owned under `/usr/lib/netmedic` next to today's helper modules.
- **Vehicle.** Gio via PyGObject (`gi.repository.Gio`), already an apt
  dependency — zero new pip supply chain (M6-consistent). Pure-Python
  D-Bus libraries were rejected to avoid a new hashed dependency for
  a root-running component.
- **Verb handling.** The service validates `verb` + JSON args with the
  existing `plan_verb()` (same `VerbValidationError` rejections the
  helper enforces today), then runs the existing `execute_plan()`
  machinery: root-owned staging, double-SHA256, `env -i` fixed `PATH`,
  `killpg` deadlines (M2), one journal record per verb (M3).

## 3. Authorization flow (first review gate — everything hangs off this)

```
caller ──Execute(verb, args)──▶ service
service:  1. plan_verb(verb, args) → reject malformed (no auth spent)
          2. spec = action_catalog.spec_for_ipc(verb's action)... (*)
          3. subject = bus-attested caller (unique name → PID/UID/unit)
          4. Authority.CheckAuthorization(subject, spec.polkit_id,
                                          allow_interaction=True)
          5. allow → execute_plan(); deny → structured denial + audit
```

(*) Method granularity note: the bus exposes **one** method, so the
method-level policy is a single permissive gate. Per-verb granularity
lives in step 2–4: the service maps the *validated* verb to its
`ActionSpec.polkit_id` (the M8 table — the same source that generates
today's policy XML) and authorizes exactly that action ID against the
attested subject. The mapping table is data; the ~30 lines performing
steps 2–4 are **security-critical code** and must be reviewed as such.
Adding a verb = adding a table row; no new methods, no policy edits.

Why this is stronger than `argv1`: `argv[1]` is caller bytes that
`pkexec` merely reports; the bus subject is attested by the bus daemon
itself (unique names cannot be spoofed by another connection; PID/UID
come from the kernel via `SO_PEERCRED`-equivalent credentials, with
PID-reuse racing closed by also binding the systemd unit where
available). `keep_auth` retention semantics from the M8 table carry
over unchanged (`auth_admin` re-prompts every call; `auth_admin_keep`
keeps its window).

Shared-verb prerequisite (found while prototyping): `vpn-run-script`
serves three operations (install/add-client/revoke) under one helper
verb, so verb→polkit-action is 1:3 ambiguous. The service MUST deny
ambiguous verbs (the prototype does). The v2.0 build track therefore
requires the deferred **M8b verb split** (distinct `vpn-install`,
`vpn-add-client`, `vpn-revoke-client` helper verbs) before any VPN
operation can move to the bus. Non-shared verbs are unaffected.

Interaction (`allow_interaction=True`) preserves today's desktop prompt
behavior; headless callers without an agent get the same explicit
"no agent" error class as today.

## 4. Threat-model delta (vs `THREAT_MODEL.md` v1.6)

| Attack | Today (pkexec) | With service |
|---|---|---|
| Caller invents root argv | Blocked by fixed verbs (F1) | Same — `plan_verb` reused |
| Venv interpreter as root | Pinned path (F3 instance fix) | **Class gone**: no interpreter path exists |
| Verb confusion across actions | `argv1` annotations (F4 instance fix) | **Class gone**: attested subject + table lookup |
| Same-UID malware + user approval | Elevation possible (residual, accepted) | Unchanged — one approval is still the boundary |
| Bus-name squatting | N/A | Mitigated: well-known name owned by root unit; systemd `BusName=` refuses takeover while the service lives |
| Downgrade to pkexec path | N/A (only path) | Pinned by install mode: D-Bus opt-in flag; daemon records which path executed each verb (audit-visible) |

`token` + `confirmed` remain *not-sufficient-alone* against same-UID
malware, exactly as today — polkit on the verb is still the real gate.

## 5. Migration (parallel through v1.x)

- Opt-in: `NETMEDIC_USE_DBUS=1` (ignored unless the bus name is owned;
  falls back to `pkexec` with a warning, never fails closed into
  unavailable-privilege confusion — the result reports the path used).
- `pkexec` stays the default; its code, policy XML and installer steps
  are untouched by this track.
- Cutover criteria for v2.0 (not this track): bus activation proven on
  all supported distros, journal evidence of zero pkexec-path verbs in
  soak, `.deb`/`.rpm` shipping the unit + policy as one transaction.

## 6. Test plan

- **Unit (no system bus):** mock Gio bus + mock authority; assert every
  `ACTIONS` row with a `polkit_id` round-trips verb→action-ID, denials
  never execute, malformed verbs never reach auth (contract test ties
  the D-Bus verb set to `action_catalog.ACTIONS` so drift fails the build).
- **Integration (VM):** `busctl` introspection, name ownership by the
  root unit, `journalctl` shows per-verb records, kill-switch test
  (stop unit → clean `helper-missing`-class error, no hang).
- **Soak:** dual-path audit comparison — same workload via both paths
  must produce identical verdicts with path labeled per record.
