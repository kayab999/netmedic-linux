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
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from netmedic.helper_verbs import (
    ALL_VERBS,
    HELPER_VERSION,
    INDEX_TXT_PATH,
    PINNED_VPN_INSTALL_SHA256,
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


def _journal_result(verb: str, ok: bool, message: str) -> None:
    """M3: root-side record of every verb outcome (tamper-evident).

    The daemon-side audit file is same-UID writable, so it cannot stand
    against the named adversary. This record is emitted as root (post-pkexec)
    to the system journal via stdlib syslog — journald captures it with the
    process credentials. Best-effort: never raises, never touches stdout
    (the JSON protocol lives there).
    """
    try:
        import syslog as _syslog

        _syslog.openlog("netmedic-helper", _syslog.LOG_PID, _syslog.LOG_AUTH)
        try:
            level = _syslog.LOG_INFO if ok else _syslog.LOG_WARNING
            _syslog.syslog(level, f"verb={verb} ok={int(ok)} {message[:300]}")
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
    """Staging dir unusable; fail closed with an integrity-class error."""


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


def _stage_verified_copy(script: str, expected: str, staging_dir: str = ROOT_STAGE_DIR) -> str:
    """Copy hash-verified script bytes into the trusted staging dir.

    Returns the staged path. Verifies source bytes, then re-verifies the
    staged bytes at the execution location — execution never reads the
    user-supplied path. Raises StagingError / returns integrity dict via caller.
    """
    try:
        with open(script, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise StagingError(f"Cannot read script: {exc}") from exc
    if _hash_bytes(data) != expected:
        raise StagingError("Security abort: Script integrity failure.")
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
        raise StagingError("Security abort: Sealed script integrity failure.")
    return staged


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
    except Exception:
        pass


def _run_argv(argv: List[str], timeout: Optional[int]) -> subprocess.CompletedProcess[str]:
    """M2: Popen + communicate + killpg (replaces subprocess.run timeout).

    subprocess.run(timeout=...) kills only the direct child; two-command
    verbs and forked VPN scripts outlived the daemon limit. Same signature
    (raises TimeoutExpired) so execute_plan is unchanged.
    """
    limit = timeout or 60
    proc = subprocess.Popen(
        argv,
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
            except Exception:
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
    proc = subprocess.Popen(
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


def _execute_vpn_script(
    marker_cmd: List[str], timeout: Optional[int], staging_dir: str = ROOT_STAGE_DIR
) -> Dict[str, Any]:
    # ["__vpn_script__", script, expected_sha, KEY=val, ...]
    if len(marker_cmd) < 3:
        return {
            "ok": False,
            "message": "Malformed vpn-run-script plan",
            "details": None,
        }
    script = marker_cmd[1]
    expected = marker_cmd[2]
    env_pairs = marker_cmd[3:]
    # F1 defense-in-depth: even if plan_verb is bypassed (in-process call),
    # the root side only honors the pin, never a caller-invented hash.
    if expected != PINNED_VPN_INSTALL_SHA256:
        return {
            "ok": False,
            "message": "Security abort: unexpected installer hash (pin mismatch).",
            "details": None,
        }
    staged: Optional[str] = None
    try:
        staged = _stage_verified_copy(script, expected, staging_dir)
    except StagingError as exc:
        return {"ok": False, "message": str(exc), "details": None}
    # F1: fixed minimal env, fixed PATH, explicit bash (also survives /run noexec
    # since bash reads the file instead of execve on a noexec mount).
    cmd = ["env", "-i", f"PATH={FIXED_PATH}", *env_pairs, FIXED_BASH, staged]
    try:
        proc = _run_argv(cmd, timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"Timeout ({timeout}s) exceeded", "details": None}
    finally:
        try:
            os.unlink(staged)
        except OSError:
            pass
    if proc.returncode == 0:
        return {
            "ok": True,
            "message": "VPN script completed",
            "details": (proc.stdout or "").strip()[:500] or None,
        }
    err = (proc.stderr or proc.stdout or "").strip()
    if "dismissed" in err.lower():
        return {"ok": False, "message": "Authentication cancelled by user", "details": err, "code": "cancelled"}
    return {
        "ok": False,
        "message": err or f"VPN script failed (exit {proc.returncode})",
        "details": None,
    }


def _read_vpn_index() -> Dict[str, Any]:
    """F2: fixed-path PKI read with O_NOFOLLOW, no cat, no caller path."""
    try:
        fd = os.open(INDEX_TXT_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        return {"ok": False, "message": f"Cannot read PKI index: {exc}", "details": None}
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return {"ok": False, "message": "PKI index is not a regular file", "details": None}
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
        return {"ok": False, "message": f"Cannot read PKI index: {exc}", "details": None}
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
        if argv and argv[0] == "__vpn_script__":
            return _execute_vpn_script(argv, timeout)
        if argv and argv[0] == "__vpn_list__":
            return _read_vpn_index()
        try:
            proc = _run_argv(argv, timeout)
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": f"Timeout ({timeout}s) exceeded",
                "details": " ".join(argv),
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
        help="Per-command timeout in seconds",
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
        return _emit({"ok": False, "message": str(exc)}, EXIT_BAD_ARGS)

    execute = _should_execute(args.execute, args.dry_run)
    if not execute:
        payload = plan_to_dict(plan, dry_run=True)
        return _emit(payload, EXIT_OK)

    result = execute_plan(plan, timeout=args.timeout)
    if result.get("ok"):
        return _emit(result, EXIT_OK)
    message = (result.get("message") or "").lower()
    if "integrity" in message or "security abort" in message:  # sf-str: allow exit-code mapping from helper payload, low-risk internal
        return _emit(result, EXIT_INTEGRITY)
    if "cancel" in message or "dismissed" in message:  # sf-str: allow helper payload code fallback, primary is code==cancelled
        return _emit(result, EXIT_CANCELLED)
    return _emit(result, EXIT_OP_FAIL)


if __name__ == "__main__":
    sys.exit(main())
