"""CLI entry for netmedic-helper (Phase B prototype).

Usage:
  netmedic-helper <verb> [--dry-run] [--json '{...}']
  netmedic-helper --list-verbs

Dry-run (default when not root and NETMEDIC_HELPER_EXECUTE is unset, or when
test mode is off) prints the planned argv sequence as JSON without running
commands. Execute mode runs the planned commands with subprocess (intended
under pkexec as root).
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import os
import re
import shlex
import signal
import stat
import subprocess
import time
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from netmedic.helper_verbs import (
    ALL_VERBS,
    HELPER_VERSION,
    INDEX_TXT_PATH,
    PINNED_VPN_INSTALL_SHA256,
    VPN_SCRIPT_PATHS,
    change_dns_apply_commands,
    change_dns_restore_command,
    change_dns_up_command,
    restart_adapter_commands,
    validate_conn_name,
    validate_dns,
    validate_iface,
    VerbPlan,
    VerbValidationError,
    plan_to_dict,
    plan_verb,
)

# Exit codes per PRIVILEGED_HELPER.md
EXIT_OK = 0
EXIT_OP_FAIL = 1
EXIT_BAD_ARGS = 2
EXIT_INTEGRITY = 3
EXIT_CANCELLED = 126

logger = logging.getLogger(__name__)


_JOURNAL_MESSAGE_MAX = 300
_JOURNAL_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _journal_uid() -> str:
    """L3: PKEXEC_UID from pkexec as a validated decimal string.

    Anything non-numeric, negative or absent becomes ``unknown`` so a caller
    cannot forge an arbitrary journal field. pkexec overwrites this variable
    in the elevated environment.
    """
    raw = os.environ.get("PKEXEC_UID", "")
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        return "unknown"
    if uid < 0:
        return "unknown"
    return str(uid)


def _journal_text(message: str) -> str:
    """Single-line, control-character-free, length-capped journal field."""
    flat = _JOURNAL_CONTROL_CHARS.sub(" ", message)
    return " ".join(flat.split())[:_JOURNAL_MESSAGE_MAX]


def _journal_result(verb: str, ok: bool, message: str) -> None:
    """M3: root-side record of every verb outcome (tamper-evident).

    The daemon-side audit file is same-UID writable, so it cannot stand
    against the named adversary. This record is emitted as root (post-pkexec)
    to the system journal via stdlib syslog — journald captures it with the
    process credentials. Best-effort: never raises, never touches stdout
    (the JSON protocol lives there).

    L3: the record names the invoking uid (PKEXEC_UID) so root actions are
    attributable, and the message is flattened so a crafted stderr line
    cannot inject a second record.
    """
    try:
        import syslog as _syslog

        line = f"verb={verb} ok={int(ok)} pkexec_uid={_journal_uid()}"
        text = _journal_text(message)
        if text:
            line = f"{line} {text}"
        _syslog.openlog("netmedic-helper", _syslog.LOG_PID, _syslog.LOG_AUTH)
        try:
            level = _syslog.LOG_INFO if ok else _syslog.LOG_WARNING
            _syslog.syslog(level, line)
        finally:
            _syslog.closelog()
    except Exception:
        logger.debug("helper journal emit failed", exc_info=True)


def _emit(payload: Dict[str, Any], code: int) -> int:
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return code


def _parse_json_args(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VerbValidationError(f"Invalid --json: {exc}") from exc
    if not isinstance(data, dict):
        raise VerbValidationError("--json must be a JSON object")
    return data


def _allow_test_execute() -> bool:
    """Honor the execute backdoor only in explicit test mode (fail-closed in production)."""
    if os.environ.get("NETMEDIC_HELPER_EXECUTE", "").lower() not in ("1", "true", "yes"):
        return False
    if os.environ.get("NETMEDIC_TEST_MODE") == "1":
        return True
    logger.warning(
        "NETMEDIC_HELPER_EXECUTE is set but ignored outside NETMEDIC_TEST_MODE (fail-closed)."
    )
    return False


def _should_execute(explicit_execute: bool, dry_run: bool) -> bool:
    if dry_run:
        return False
    if explicit_execute:
        return True
    # Default: execute only when already root (pkexec path) or test env forces it.
    if _allow_test_execute():
        return True
    return os.geteuid() == 0


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Root-owned staging for verified scripts (C-1). The daemon stages into a
# user-owned dir, so the helper must never execute from there: a same-UID
# attacker could swap bytes between the helper's hash check and exec.
# Staging here is owned by the executing UID (root under pkexec), mode 0700,
# unique per invocation — the swap window no longer exists.
ROOT_STAGE_DIR = "/run/netmedic"


class StagingError(Exception):
    """Staging dir unusable or installer integrity failed; fail closed.

    ``code`` is the structured result code consumed by ``main`` so the exit
    status never depends on human-readable text.
    """

    def __init__(self, message: str, *, code: str = "op_fail") -> None:
        super().__init__(message)
        self.code = code


def _ensure_root_stage_dir(staging_dir: str = ROOT_STAGE_DIR) -> Path:
    """Return a trusted staging dir or raise StagingError.

    Trust = real directory, owned by our own euid (root under pkexec),
    mode 0700. A pre-created attacker-owned/symlinked dir is refused —
    chmod alone would not help (owner keeps write bits).
    """
    try:
        os.makedirs(staging_dir, mode=0o700, exist_ok=True)
    except OSError as exc:
        raise StagingError(f"Cannot create staging dir {staging_dir}: {exc}") from exc
    try:
        st = os.lstat(staging_dir)
    except OSError as exc:
        raise StagingError(f"Cannot stat staging dir {staging_dir}: {exc}") from exc
    if not stat.S_ISDIR(st.st_mode):
        raise StagingError(f"Staging path is not a directory: {staging_dir}")
    if st.st_uid != os.geteuid():
        raise StagingError(
            f"Refusing staging dir not owned by euid {os.geteuid()}: {staging_dir}"
        )
    try:
        os.chmod(staging_dir, 0o700)
    except OSError as exc:
        raise StagingError(f"Cannot secure staging dir {staging_dir}: {exc}") from exc
    return Path(staging_dir)


def _stage_verified_bytes(data: bytes, expected: str, staging_dir: str = ROOT_STAGE_DIR) -> str:
    """Write verified installer bytes into the trusted staging dir.

    Returns the staged path. Re-verifies the staged bytes at the execution
    location -- execution never reads the system path. Raises StagingError.
    """
    if _hash_bytes(data) != expected:
        raise StagingError("Security abort: Script integrity failure.", code="integrity")
    staged_dir = _ensure_root_stage_dir(staging_dir)
    fd, staged = tempfile.mkstemp(prefix="sealed-", suffix=".sh", dir=str(staged_dir))
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)
    # Re-hash AT the execution location: the staged bytes are what will exec.
    if _hash_file(staged) != expected:
        try:
            os.unlink(staged)
        except OSError:
            pass
        raise StagingError("Security abort: Sealed script integrity failure.", code="integrity")
    return staged


# F2: generous cap for the vendored installer (147 KiB at pin time).
VPN_SCRIPT_MAX_BYTES = 1 << 20
# Separate (smaller) cap for a delivered .ovpn artifact.
VPN_ARTIFACT_MAX_BYTES = 256 * 1024


def _read_vpn_script(script_id: str) -> bytes:
    """Read the fixed root-owned installer named by *script_id*.

    The id resolves against a constant map -- the caller never supplies a
    path. Symlinks, non-regular files, foreign owners, writable modes and
    oversized files fail closed. The SHA256 of the bytes actually read must
    equal the root-side pin.
    """
    path = VPN_SCRIPT_PATHS.get(script_id)
    if path is None:
        raise StagingError(f"Unknown script_id: {script_id!r}")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise StagingError(f"Cannot read installer {path}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise StagingError(f"Refusing installer that is not a regular file: {path}")
        if st.st_uid != os.geteuid():
            raise StagingError(f"Refusing installer not owned by euid {os.geteuid()}: {path}")
        if st.st_mode & 0o022:
            raise StagingError(f"Refusing writable installer: {path}")
        if st.st_size == 0:
            raise StagingError(f"Refusing empty installer: {path}")
        if st.st_size > VPN_SCRIPT_MAX_BYTES:
            raise StagingError(
                f"Refusing installer that is too large ({VPN_SCRIPT_MAX_BYTES} bytes max): {path}"
            )
        chunks: List[bytes] = []
        remaining = VPN_SCRIPT_MAX_BYTES + 1
        while remaining > 0:
            block = os.read(fd, min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    if len(data) > VPN_SCRIPT_MAX_BYTES:
        raise StagingError(
            f"Refusing installer that is too large ({VPN_SCRIPT_MAX_BYTES} bytes max): {path}"
        )
    if _hash_bytes(data) != PINNED_VPN_INSTALL_SHA256:
        raise StagingError("Security abort: Script integrity failure.", code="integrity")
    return data


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    """M2: kill the whole group, not just the direct child.

    Verbs like renew-ip run two commands and VPN scripts fork; killing only
    the leader orphans root children that outlive the daemon timeout.
    Runs as the same euid as the children (root under pkexec), so killpg
    succeeds here — unlike the daemon side after setuid (see system.py).
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        proc.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        proc.wait(timeout=2)
    except Exception:  # noqa: S110 (best-effort re-kill during timeout cleanup; proc already reaped or dead)
        pass


def _run_argv(argv: List[str], timeout: Optional[float]) -> subprocess.CompletedProcess[str]:
    """M2: Popen + communicate + killpg (replaces subprocess.run timeout).

    subprocess.run(timeout=...) kills only the direct child; two-command
    verbs and forked VPN scripts outlived the daemon limit. Same signature
    (raises TimeoutExpired) so execute_plan is unchanged.
    """
    limit = timeout if timeout is not None else 60.0
    proc = subprocess.Popen(  # noqa: S603 (fixed argv from VerbPlan allowlist; no shell)
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except Exception:
            stdout, stderr = "", ""
            try:
                proc.kill()
            except Exception:  # noqa: S110 (best-effort kill of timed-out child; killpg already ran)
                pass
        raise subprocess.TimeoutExpired(proc.args, limit, output=stdout, stderr=stderr) from None
    return subprocess.CompletedProcess(proc.args, proc.returncode or 0, stdout, stderr)


@dataclasses.dataclass
class DeadlineResult:
    """M2: outcome of deadline-enforced execution (JSON-serializable)."""

    stdout: str
    stderr: str
    exit_code: int
    elapsed: float
    timeout: bool
    process_group_killed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "elapsed": self.elapsed,
            "timeout": self.timeout,
            "process_group_killed": self.process_group_killed,
        }


def execute_with_deadline(
    command: List[str],
    deadline: float = 30.0,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> DeadlineResult:
    """M2: run *command* with a hard process-group deadline (no signals).

    Uses Popen + killpg only (no SIGALRM: not thread-safe, breaks pytest).
    Default env is the F1 fixed minimal env when caller passes none.
    """
    import time as _time

    start = _time.time()
    base_env = {"PATH": FIXED_PATH, "HOME": "/root", "TERM": "dumb"}
    if env is not None:
        base_env = dict(env)
    proc = subprocess.Popen(  # noqa: S603 (fixed argv (/bin/bash + staged root-owned script); no shell)
        command,
        preexec_fn=os.setsid,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=base_env,
        cwd=cwd,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=deadline)
        return DeadlineResult(
            stdout=stdout or "",
            stderr=stderr or "",
            exit_code=proc.returncode or 0,
            elapsed=_time.time() - start,
            timeout=False,
            process_group_killed=False,
        )
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except Exception:
            stdout, stderr = "", ""
        return DeadlineResult(
            stdout=stdout or "",
            stderr=((stderr or "") + f"\n[M2] Deadline exceeded: {deadline}s. Process group killed.").strip(),
            exit_code=-signal.SIGKILL,
            elapsed=_time.time() - start,
            timeout=True,
            process_group_killed=True,
        )


FIXED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
FIXED_BASH = "/bin/bash"


def _execute_vpn_cli(
    marker_cmd: List[str], timeout: Optional[int], staging_dir: str = ROOT_STAGE_DIR
) -> Dict[str, Any]:
    # ["__vpn_cli__", <subcommand + flags...>]
    if len(marker_cmd) < 2:
        return {
            "ok": False,
            "message": "Malformed vpn verb plan",
            "details": None,
        }
    script_args = list(marker_cmd[1:])

    # For `client add`, stage a sealed output path so the root helper (not the
    # daemon) owns the .ovpn landing spot; the helper reads it back and deletes
    # it. Root never writes into $HOME.
    is_add = (
        len(script_args) >= 2
        and script_args[0] == "client"
        and script_args[1] == "add"
    )
    out_path: Optional[str] = None
    extra_flags: List[str] = []
    if is_add:
        client_name = script_args[2] if len(script_args) > 2 else "client"
        try:
            stage_dir = _ensure_root_stage_dir(staging_dir)
        except StagingError as exc:
            return {"ok": False, "message": str(exc), "details": None, "code": exc.code}
        fd, out_path = tempfile.mkstemp(
            prefix=f"{client_name}-", suffix=".ovpn", dir=str(stage_dir)
        )
        os.close(fd)
        try:
            os.unlink(out_path)
        except OSError:
            pass
        extra_flags = ["--output", out_path]

    staged: Optional[str] = None
    try:
        data = _read_vpn_script("openvpn-install")
        staged = _stage_verified_bytes(data, PINNED_VPN_INSTALL_SHA256, staging_dir)
    except StagingError as exc:
        if out_path is not None:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        return {"ok": False, "message": str(exc), "details": None, "code": exc.code}

    # F3: fixed minimal env, fixed PATH, explicit bash (survives noexec mounts).
    cmd = ["env", "-i", f"PATH={FIXED_PATH}", FIXED_BASH, staged, *script_args, *extra_flags]
    try:
        proc = _run_argv(cmd, timeout)
    except subprocess.TimeoutExpired:
        if staged is not None:
            try:
                os.unlink(staged)
            except OSError:
                pass
        if out_path is not None:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        return {
            "ok": False,
            "message": f"Timeout ({timeout}s) exceeded",
            "details": None,
            "code": "op_fail",
        }
    finally:
        if staged is not None:
            try:
                os.unlink(staged)
            except OSError:
                pass

    artifact: Optional[str] = None
    if proc.returncode == 0 and is_add and out_path is not None and os.path.exists(out_path):
        try:
            fd = os.open(out_path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                st = os.fstat(fd)
                if stat.S_ISREG(st.st_mode) and 0 < st.st_size <= VPN_ARTIFACT_MAX_BYTES:
                    chunks: List[bytes] = []
                    remaining = VPN_ARTIFACT_MAX_BYTES + 1
                    while remaining > 0:
                        block = os.read(fd, min(65536, remaining))
                        if not block:
                            break
                        chunks.append(block)
                        remaining -= len(block)
                    raw = b"".join(chunks)
                    if len(raw) <= VPN_ARTIFACT_MAX_BYTES:
                        artifact = raw.decode("utf-8", errors="replace")
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass
        except OSError:
            artifact = None
        try:
            os.unlink(out_path)
        except OSError:
            pass
        out_path = None

    if out_path is not None:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    if proc.returncode == 0:
        result: Dict[str, Any] = {
            "ok": True,
            "message": "VPN command completed",
            "details": (proc.stdout or "").strip() or None,
        }
        if artifact is not None:
            result["artifact"] = artifact
        return result
    err = (proc.stderr or proc.stdout or "").strip()
    if "dismissed" in err.lower():
        return {"ok": False, "message": "Authentication cancelled by user", "details": err, "code": "cancelled"}
    return {
        "ok": False,
        "message": err or f"VPN command failed (exit {proc.returncode})",
        "details": None,
        "code": "op_fail",
    }


CommandExecutor = Callable[[List[str], Optional[float]], subprocess.CompletedProcess[str]]
Clock = Callable[[], float]


def _run_with_budget(
    executor: CommandExecutor,
    argv: List[str],
    deadline: float,
    clock: Clock,
) -> Tuple[Optional[subprocess.CompletedProcess[str]], bool]:
    """Run *argv* with the time left before *deadline*.

    Returns (process, timed_out). A command that would start after the
    deadline is not started at all: the caller must treat it as a timeout so
    the overall verb deadline is never exceeded.
    """
    remaining = deadline - clock()
    if remaining <= 0:
        return None, True
    try:
        return executor(argv, remaining), False
    except subprocess.TimeoutExpired:
        return None, True


def _change_dns_abort(message: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "message": message,
        "details": "stage=snapshot; config=unchanged",
    }


def _manual_dns_restore(conn: str, dns: str, ignore_auto_dns: str) -> str:
    return (
        "nmcli con mod "
        f"{shlex.quote(conn)} ipv4.dns {shlex.quote(dns)} "
        f"ipv4.ignore-auto-dns {shlex.quote(ignore_auto_dns)}"
    )


def _execute_change_dns(
    plan: VerbPlan,
    timeout: float,
    *,
    executor: Optional[CommandExecutor] = None,
    clock: Optional[Clock] = None,
) -> Dict[str, Any]:
    """Apply DNS with a single deadline and a reserved rollback slice.

    The caller supplies nothing to restore: both previous properties are read
    as root before any change and revalidated here. Every command receives
    only the time left in its phase, so the sum of the command limits can
    never exceed the verb deadline.
    """
    run = executor or _run_argv
    now = clock or time.monotonic
    try:
        conn = validate_conn_name(str(plan.params.get("connection") or ""))
        server = validate_dns(str(plan.params.get("server") or ""))
    except VerbValidationError:
        return {"ok": False, "message": "Malformed change-dns plan", "details": None, "code": "op_fail"}
    if plan.commands != change_dns_apply_commands(conn, server):
        return {"ok": False, "message": "Malformed change-dns plan", "details": None, "code": "op_fail"}

    total = float(timeout)
    reserve = min(10.0, total / 3.0)
    start = now()
    apply_deadline = start + (total - reserve)
    rollback_deadline = start + total

    # 1. Snapshot BOTH properties, fail-closed before anything is modified.
    dns_proc, dns_to = _run_with_budget(
        run,
        ["nmcli", "-g", "ipv4.dns", "connection", "show", conn],
        apply_deadline,
        now,
    )
    if dns_to or dns_proc is None:
        return _change_dns_abort("Timeout during snapshot; no changes made")
    if dns_proc.returncode != 0:
        return _change_dns_abort("Snapshot failed (ipv4.dns); no changes made")

    ign_proc, ign_to = _run_with_budget(
        run,
        ["nmcli", "-g", "ipv4.ignore-auto-dns", "connection", "show", conn],
        apply_deadline,
        now,
    )
    if ign_to or ign_proc is None:
        return _change_dns_abort("Timeout during snapshot; no changes made")
    if ign_proc.returncode != 0:
        return _change_dns_abort("Snapshot failed (ipv4.ignore-auto-dns); no changes made")

    prev_dns_tokens = [
        token
        for token in (dns_proc.stdout or "").replace(",", " ").split()
        if token
    ]
    try:
        for token in prev_dns_tokens:
            validate_dns(token)
    except VerbValidationError:
        return _change_dns_abort("Snapshot invalid (prev DNS); no changes made")

    prev_ignore = (ign_proc.stdout or "").strip().lower()
    if prev_ignore not in ("yes", "no"):
        return _change_dns_abort(
            "Snapshot invalid (ignore-auto-dns); no changes made"
        )
    prev_dns = ",".join(prev_dns_tokens)

    # 2. Apply the exact argv the dry-run showed.
    mod_proc, mod_to = _run_with_budget(run, plan.commands[0], apply_deadline, now)
    if mod_to or mod_proc is None or mod_proc.returncode != 0:
        failed_stage = "con-mod"
    else:
        up_proc, up_to = _run_with_budget(
            run, plan.commands[1], apply_deadline, now
        )
        if up_to or up_proc is None or up_proc.returncode != 0:
            failed_stage = "con-up"
        else:
            return {
                "ok": True,
                "message": f"DNS set to {server} on {conn}",
                "details": None,
            }

    # 3. Restore the config FIRST, then try to reactivate best-effort.
    restore_proc, restore_to = _run_with_budget(
        run,
        change_dns_restore_command(conn, prev_dns, prev_ignore),
        rollback_deadline,
        now,
    )
    restored = (
        not restore_to
        and restore_proc is not None
        and restore_proc.returncode == 0
    )
    if restored:
        _run_with_budget(
            run,
            change_dns_up_command(conn),
            rollback_deadline,
            now,
        )
        _journal_result(
            "change-dns-rollback",
            True,
            f"config reverted to {prev_dns or '(empty)'}; reactivation unconfirmed",
        )
        return {
            "ok": False,
            "message": (
                f"DNS change failed at {failed_stage}; config reverted to "
                f"{prev_dns or '(empty)'}; connection reactivation not confirmed"
            ),
            "details": (
                f"stage={failed_stage}; config=reverted; "
                "reactivation=unconfirmed"
            ),
        }

    manual = _manual_dns_restore(conn, prev_dns, prev_ignore)
    _journal_result("change-dns-rollback", False, f"FAILED; manual={manual}")
    return {
        "ok": False,
        "message": (
            f"DNS change failed at {failed_stage}; rollback FAILED: "
            f"run manually {manual}"
        ),
        "details": f"stage={failed_stage}; config=not-restored; manual={manual}",
    }


def _read_hex_file(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip(), 16)
    except (OSError, ValueError):
        return None


def _read_carrier(path: Path) -> Optional[bool]:
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    if text == "1":
        return True
    if text == "0":
        return False
    return None


def _execute_restart_adapter(
    plan: VerbPlan,
    timeout: Optional[float],
    *,
    executor: Optional[CommandExecutor] = None,
    clock: Optional[Clock] = None,
    sysfs_root: Path = Path("/sys/class/net"),
) -> Dict[str, Any]:
    """Cycle an interface and report its real final state.

    ``operstate`` is not used: lo/dummy report "unknown" while being UP.
    IFF_UP and carrier are read from sysfs; a missing carrier file means
    "unknown", not failure. If the first `up` times out, one final attempt
    runs inside the remaining budget.
    """
    run = executor or _run_argv
    now = clock or time.monotonic
    try:
        iface = validate_iface(str(plan.params.get("iface") or ""))
    except VerbValidationError:
        return {"ok": False, "message": "Malformed restart-adapter plan", "details": None, "code": "op_fail"}
    if plan.commands != restart_adapter_commands(iface):
        return {"ok": False, "message": "Malformed restart-adapter plan", "details": None, "code": "op_fail"}

    total = float(timeout if timeout is not None else 60.0)
    start = now()
    deadline = start + total

    down_budget = min(deadline - now(), max(total / 3.0, 0.1))
    if down_budget > 0:
        try:
            run(plan.commands[0], down_budget)
        except subprocess.TimeoutExpired:
            pass

    for attempt in range(2):
        remaining = deadline - now()
        if remaining <= 0:
            break
        budget = remaining if attempt == 1 else remaining / 2.0
        try:
            proc = run(plan.commands[1], budget)
        except subprocess.TimeoutExpired:
            continue
        if proc.returncode == 0:
            break

    flags = _read_hex_file(sysfs_root / iface / "flags")
    iff_up: Optional[bool] = None if flags is None else bool(flags & 0x1)
    carrier = _read_carrier(sysfs_root / iface / "carrier")
    iff_state = "unknown" if iff_up is None else ("up" if iff_up else "down")
    carrier_state = (
        "unknown" if carrier is None else ("up" if carrier else "down")
    )
    details = f"iff_up={iff_state}; carrier={carrier_state}"

    if iff_up:
        if carrier is True:
            message = f"Adapter {iface} is UP (carrier detected)"
        elif carrier is False:
            message = f"Adapter {iface} is UP (no carrier)"
        else:
            message = f"Adapter {iface} is UP (carrier unknown)"
        return {"ok": True, "message": message, "details": details}

    return {
        "ok": False,
        "message": f"Adapter {iface} not UP after restart",
        "details": details,
    }


def _read_vpn_index() -> Dict[str, Any]:
    """F2: fixed-path PKI read with O_NOFOLLOW, no cat, no caller path."""
    try:
        fd = os.open(INDEX_TXT_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        return {"ok": False, "message": f"Cannot read PKI index: {exc}", "details": None, "code": "op_fail"}
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return {"ok": False, "message": "PKI index is not a regular file", "details": None, "code": "op_fail"}
        # 1 MiB cap (matches audit: subprocess output must be size-capped).
        chunks: List[bytes] = []
        remaining = 1 << 20
        while remaining > 0:
            block = os.read(fd, min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks).decode("utf-8", errors="replace").strip()[:20000]
        return {"ok": True, "message": "read VPN PKI index", "details": data or None, "verb": "vpn-list"}
    except OSError as exc:
        return {"ok": False, "message": f"Cannot read PKI index: {exc}", "details": None, "code": "op_fail"}
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def execute_plan(plan: VerbPlan, *, timeout: Optional[int] = None) -> Dict[str, Any]:
    """Run planned commands; return helper JSON payload.

    M3: exactly one root-side journal record per verb execution, whatever
    the outcome (success, op failure, integrity abort, timeout).
    """
    result = _execute_plan_inner(plan, timeout=timeout)
    _journal_result(plan.verb, bool(result.get("ok")), str(result.get("message") or ""))
    return result


def _execute_plan_inner(plan: VerbPlan, *, timeout: Optional[int] = None) -> Dict[str, Any]:
    """Run planned commands; return helper JSON payload."""
    outputs: List[str] = []
    for argv in plan.commands:
        if argv and argv[0] == "__vpn_cli__":
            return _execute_vpn_cli(argv, timeout)
        if argv and argv[0] == "__vpn_list__":
            return _read_vpn_index()
        if plan.verb == "change-dns":
            return _execute_change_dns(
                plan, float(timeout if timeout is not None else 60)
            )
        if plan.verb == "restart-adapter":
            return _execute_restart_adapter(plan, timeout)
        try:
            proc = _run_argv(argv, timeout)
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": f"Timeout ({timeout}s) exceeded",
                "details": " ".join(argv),
                "code": "op_fail",
            }
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if "dismissed" in err.lower():
                return {
                    "ok": False,
                    "message": "Authentication cancelled by user",
                    "details": err,
                    "code": "cancelled",
                }
            return {
                "ok": False,
                "message": err or f"Command failed (exit {proc.returncode})",
                "details": " ".join(argv),
                "code": "op_fail",
            }
        if proc.stdout:
            outputs.append(proc.stdout.strip())
    return {
        "ok": True,
        "message": plan.message or "ok",
        "details": "\n".join(outputs) if outputs else None,
        "verb": plan.verb,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netmedic-helper",
        description="NetMedic fixed-verb privileged helper (Phase B prototype)",
    )
    parser.add_argument(
        "verb",
        nargs="?",
        help="Helper verb (see --list-verbs)",
    )
    parser.add_argument(
        "--json",
        dest="json_args",
        default=None,
        help="JSON object of verb arguments",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned commands without executing",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Force execution even when not root",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help=(
            "Total deadline in seconds for the whole verb (all commands share "
            "it); the daemon waits this deadline plus the IPC margin"
        ),
    )
    parser.add_argument(
        "--list-verbs",
        action="store_true",
        help="List supported verbs and exit",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print helper version and exit",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.version:
        return _emit({"ok": True, "version": HELPER_VERSION}, EXIT_OK)

    if args.list_verbs:
        return _emit({"ok": True, "verbs": sorted(ALL_VERBS)}, EXIT_OK)

    if not args.verb:
        parser.error("verb is required (or use --list-verbs)")

    try:
        verb_args = _parse_json_args(args.json_args)
        plan = plan_verb(args.verb, verb_args)
    except VerbValidationError as exc:
        return _emit({"ok": False, "message": str(exc), "code": "bad_args"}, EXIT_BAD_ARGS)

    execute = _should_execute(args.execute, args.dry_run)
    if not execute:
        payload = plan_to_dict(plan, dry_run=True)
        return _emit(payload, EXIT_OK)

    result = execute_plan(plan, timeout=args.timeout)
    if result.get("ok"):
        return _emit(result, EXIT_OK)
    # Structured mapping only: never infer a security-relevant exit code from
    # human-readable text (issue #52). Missing codes are operational failures.
    code = result.get("code")
    if code == "integrity":
        return _emit(result, EXIT_INTEGRITY)
    if code == "cancelled":
        return _emit(result, EXIT_CANCELLED)
    if code == "bad_args":
        return _emit(result, EXIT_BAD_ARGS)
    return _emit(result, EXIT_OP_FAIL)


if __name__ == "__main__":
    sys.exit(main())
