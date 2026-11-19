import json
import logging
import os
import re
import signal
import stat
import subprocess
from typing import Any, FrozenSet, List, Mapping, Optional

from netmedic.models import CommandResult
from netmedic.config import Config
from netmedic.helper_verbs import HELPER_VERSION, VerbValidationError, plan_verb

logger = logging.getLogger(__name__)

# M2: IPC margin (seconds) added to the helper deadline for the daemon-side
# wait. The helper enforces the bare deadline via process-group kill; the
# daemon must not fire first.
_IPC_MARGIN_FALLBACK = 5

# L1: elevation wrapper is a fixed system path. Resolving it through PATH
# would let a writable directory earlier in PATH capture the admin password.
PKEXEC_PATH = "/usr/bin/pkexec"


def _check_pkexec_stat(st: os.stat_result, path: str) -> None:
    """Reject pkexec unless it is a root-owned, executable regular file."""
    if not stat.S_ISREG(st.st_mode):
        raise PermissionError(f"Refusing pkexec that is not a regular file: {path}")
    if st.st_uid != 0:
        raise PermissionError(
            f"Refusing pkexec not owned by root: {path} (uid={st.st_uid})"
        )
    if not (st.st_mode & 0o111):
        raise PermissionError(f"Refusing non-executable pkexec: {path}")


def _validated_pkexec() -> str:
    """Return the fixed pkexec path after validating its on-disk identity.

    M1/L1: no shutil.which. The path is a compile-time constant; only its
    metadata is checked so a swapped binary fails closed.
    """
    try:
        st = os.stat(PKEXEC_PATH)
    except OSError as exc:
        raise FileNotFoundError(f"pkexec not found at {PKEXEC_PATH}: {exc}") from exc
    _check_pkexec_stat(st, PKEXEC_PATH)
    return PKEXEC_PATH


# Basenames allowed under require_root=True. Path is the absolute binary or
# the fixed pkexec wrapper; argv shape is still caller-controlled within these
# tools.
# NOTE: bash/sh removed (P0 hardening) — no legit elevated path needs a shell;
# VPN scripts run via `env VAR=... /abs/path` + SHA256 sealed copy in helper.
_ROOT_ALLOWED_BINARIES: FrozenSet[str] = frozenset({
    "pkexec",  # never used as target; elevation wrapper only
    "resolvectl",
    "nmcli",
    "dhclient",
    "systemctl",
    "ip",
    "ufw",
    "cat",
    "env",  # Angristan script launcher: env VAR=... /path/to/script
})


class CommandRunner:
    # M2: extra seconds the daemon waits beyond the helper deadline.
    _IPC_MARGIN = _IPC_MARGIN_FALLBACK

    SENSITIVE_PATTERNS = [
        r"(?i)password",
        r"(?i)pass",
        r"(?i)token",
        r"(?i)key",
        r"(?i)secret",
        r"(?i)auth",
    ]

    @staticmethod
    def _redact_command(command: List[str]) -> str:
        """Redact potentially sensitive arguments for logging."""
        redacted = []
        it = iter(command)
        for arg in it:
            if "=" in arg:
                parts = arg.split("=", 1)
                key = parts[0]
                if any(re.search(p, key) for p in CommandRunner.SENSITIVE_PATTERNS):
                    redacted.append(f"{key}=<REDACTED>")
                else:
                    redacted.append(arg)
            elif any(re.search(p, arg) for p in CommandRunner.SENSITIVE_PATTERNS):
                redacted.append(arg)
                try:
                    val = next(it)
                    if val.startswith("-"):
                        redacted.append(val)
                    else:
                        redacted.append("<REDACTED>")
                except StopIteration:
                    break
            else:
                redacted.append(arg)
        return " ".join(redacted)

    @staticmethod
    def _binary_basename(command: List[str]) -> str:
        if not command:
            return ""
        return os.path.basename(command[0])

    @staticmethod
    def _assert_root_command_allowed(command: List[str]) -> Optional[str]:
        """Return an error string if elevated command is outside the allowlist."""
        if not command:
            return "Empty command cannot be elevated."
        basename = CommandRunner._binary_basename(command)
        if basename not in _ROOT_ALLOWED_BINARIES or basename == "pkexec":
            return f"Elevated command not allowlisted: {basename or '<empty>'}"
        # Refuse shell metacharacters / path tricks in binary path
        if ".." in command[0] or "\x00" in command[0]:
            return "Invalid elevated command path."
        # env is only used to launch operator scripts with fixed VAR=value form
        if basename == "env":
            for arg in command[1:]:
                if arg.startswith("-"):
                    return "Elevated env: flags are not allowed."
                if "=" not in arg:
                    # Remainder is the script path
                    break
            else:
                return "Elevated env: missing script path."
        return None

    @staticmethod
    def _helper_version_argv() -> List[str]:
        """Argv to query helper --version without elevation."""
        helper = str(Config.get_helper_path())
        if "|" in helper and helper.count("|") >= 2:
            parts = helper.split("|")
            return [parts[0], parts[1], parts[2], "--version"]
        return [helper, "--version"]

    @staticmethod
    def _check_helper_version() -> Optional[str]:
        """F5: refuse a stale or unreadable system helper.

        Fail closed: elevation is allowed only when the probe exits 0, returns
        a JSON object with ``ok is True`` and an exact ``HELPER_VERSION``
        match. Anything else (missing helper, timeout, rc != 0, invalid JSON,
        ok=false, empty version) blocks privileged operations. The dev
        ``python -m`` marker keeps its explicit in-repo fallback.
        """
        # Dev fallback (python -m) always matches in-repo version.
        helper = str(Config.get_helper_path())
        if "|" in helper:
            return None

        def blocked(reason: str) -> str:
            return (
                f"Privileged helper version check failed: {reason}. "
                "Re-run: ./scripts/install-polkit-policy.sh"
            )

        try:
            proc = subprocess.run(  # noqa: S603 (fixed argv (helper path + verb + JSON); no shell)
                CommandRunner._helper_version_argv(),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return blocked("probe timed out")
        except Exception as exc:
            return blocked(f"probe failed ({exc})")

        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().splitlines()
            suffix = f": {detail[-1]}" if detail else ""
            return blocked(f"helper --version exited rc={proc.returncode}{suffix}")

        raw = (proc.stdout or "").strip()
        if not raw:
            return blocked("helper --version produced no output")
        try:
            payload = json.loads(raw.splitlines()[-1])
        except (IndexError, ValueError):
            return blocked("helper --version returned invalid JSON")
        if not isinstance(payload, dict):
            return blocked("helper --version returned an invalid payload")
        if payload.get("ok") is not True:
            return blocked("helper --version did not report ok=true")
        ver = payload.get("version")
        if not isinstance(ver, str) or not ver.strip():
            return blocked("helper --version reported no version")
        if ver != HELPER_VERSION:
            return blocked(f"version mismatch (have {ver}, want {HELPER_VERSION})")
        return None

    @staticmethod
    def _helper_invocation(verb: str, args: Mapping[str, Any], *, timeout: Optional[float]) -> List[str]:
        """Build argv to run netmedic-helper (optionally under pkexec)."""
        helper = str(Config.get_helper_path())
        json_args = json.dumps(dict(args), separators=(",", ":"))
        if "|" in helper and helper.count("|") >= 2:
            # Dev marker: python|-m|netmedic.helper_main
            parts = helper.split("|")
            base = [parts[0], parts[1], parts[2], verb, "--execute", "--json", json_args]
        else:
            base = [helper, verb, "--execute", "--json", json_args]
        if timeout is not None:
            base.extend(["--timeout", str(int(timeout))])
        if os.geteuid() != 0:
            return [_validated_pkexec()] + base
        return base

    @staticmethod
    def run_elevated(
        verb: str,
        args: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        """Run a fixed helper verb (Phase D production path).

        Production: pkexec netmedic-helper <verb> --execute --json ...
        Legacy (tests only): NETMEDIC_USE_HELPER=0 + NETMEDIC_ALLOW_LEGACY_ELEVATION=1
        expands plan_verb() to raw tool argv under pkexec.
        """
        if timeout is None:
            timeout = Config.get_default_timeout()
        args = dict(args or {})

        try:
            plan = plan_verb(verb, args)
        except VerbValidationError as exc:
            return CommandResult(False, 2, "", str(exc), [verb])

        if Config.use_privileged_helper():
            ver_err = CommandRunner._check_helper_version()
            if ver_err:
                return CommandResult(False, 127, "", ver_err, [verb])
            # M2: one deadline for the whole verb, enforced inside the helper
            # via killpg. The daemon timeout is helper deadline + IPC margin so
            # the daemon never reports a timeout while root work continues and
            # retries overlap. Helper gets the bare deadline (--timeout).
            daemon_timeout = timeout + CommandRunner._IPC_MARGIN
            try:
                final_cmd = CommandRunner._helper_invocation(verb, args, timeout=timeout)
            except OSError as exc:
                # FileNotFoundError (missing) or PermissionError (unsafe binary).
                return CommandResult(False, 127, "", str(exc), [verb])
            # Helper elevates via pkexec; do not double-wrap.
            # C-9: run() contains its own timeout, but never let a timeout
            # escape as a traceback — headless with no polkit agent must get
            # a structured result, never a hang or an unhandled exception.
            try:
                result = CommandRunner.run(final_cmd, require_root=False, timeout=daemon_timeout)
            except subprocess.TimeoutExpired:
                return CommandResult(False, -1, "", f"Timeout ({daemon_timeout}s) exceeded", final_cmd)
            if result.stdout:
                try:
                    payload = json.loads(result.stdout.splitlines()[-1])
                    if isinstance(payload, dict) and "ok" in payload:
                        ok = bool(payload.get("ok"))
                        msg = str(payload.get("message") or "")
                        details = payload.get("details")
                        code = payload.get("code")
                        artifact = payload.get("artifact")
                        out = "" if details is None else str(details)
                        # PR2: propagate cancelled via code, not locale string
                        if not ok and code == "cancelled":
                            return CommandResult(
                                False,
                                126,
                                "",
                                "Authentication cancelled by user",
                                result.command,
                                message="Authentication cancelled by user",
                            )
                        if not ok and result.returncode == 126:
                            # pkexec dismissal already surfaced as 126
                            cancel_msg = msg or "Authentication cancelled by user"
                            return CommandResult(
                                False,
                                126,
                                "",
                                cancel_msg,
                                result.command,
                                message=cancel_msg,
                            )
                        return CommandResult(
                            ok,
                            0 if ok else (result.returncode or 1),
                            out if ok else result.stdout,
                            "" if ok else msg,
                            result.command,
                            artifact if (isinstance(artifact, str) or artifact is None) else None,
                            message=msg,
                            details=details,
                        )
                except json.JSONDecodeError:
                    pass
            # Also handle direct pkexec cancellation without JSON payload (require_root case)
            if result.returncode == 126 and not result.stdout:
                stderr_low = (result.stderr or "").lower()
                if "cancel" in stderr_low or "dismissed" in stderr_low:
                    return CommandResult(False, 126, "", "Authentication cancelled by user", result.command)
            return result

        if not Config.allow_legacy_elevation():
            # Distinct from 126 auth-cancel: use 127 + explicit helper-missing hint
            return CommandResult(
                False,
                127,
                "",
                (
                    "Privileged helper not installed (helper-missing). "
                    "Run: ./scripts/install-polkit-policy.sh "
                    "then: netmedic --status "
                    "(helper provides fixed-verb root elevation)."
                ),
                [verb],
            )

        # Legacy path (tests / emergency): planned argv via raw pkexec.
        last = CommandResult(False, -1, "", "No commands planned", [verb])
        for argv in plan.commands:
            if argv and argv[0] == "__vpn_script__":
                script = argv[1]
                env_pairs = argv[3:]
                legacy = ["env", *env_pairs, script]
            else:
                legacy = argv
            try:
                last = CommandRunner.run(
                    legacy, require_root=True, timeout=timeout, _legacy_ok=True
                )
            except subprocess.TimeoutExpired:
                return CommandResult(False, -1, "", f"Timeout ({timeout}s) exceeded", legacy)
            if not last.success:
                return last
        return last

    @staticmethod
    def run(
        command: List[str],
        require_root: bool = False,
        timeout: Optional[float] = None,
        *,
        _legacy_ok: bool = False,
    ) -> CommandResult:
        """
        Execute commands with timeout, optional elevation, and sanitized logging.

        Phase D: require_root=True is blocked unless NETMEDIC_ALLOW_LEGACY_ELEVATION
        (or internal _legacy_ok from run_elevated's legacy branch). Production
        elevation must use run_elevated() → netmedic-helper.
        """
        if timeout is None:
            timeout = Config.get_default_timeout()

        final_cmd = list(command)

        if require_root and os.geteuid() != 0:
            if not (_legacy_ok or Config.allow_legacy_elevation()):
                msg = (
                    "Direct root elevation is disabled. Use CommandRunner.run_elevated "
                    "with a fixed helper verb, or install the system helper."
                )
                logger.error(msg)
                return CommandResult(False, 126, "", msg, final_cmd)
            allow_err = CommandRunner._assert_root_command_allowed(final_cmd)
            if allow_err:
                logger.error(allow_err)
                return CommandResult(False, 126, "", allow_err, final_cmd)
            try:
                pkexec = _validated_pkexec()
            except OSError as exc:
                logger.error("pkexec unavailable, cannot elevate privileges: %s", exc)
                return CommandResult(False, 127, "", str(exc), final_cmd)
            final_cmd = [pkexec] + final_cmd

        cmd_str_redacted = CommandRunner._redact_command(final_cmd)
        logger.debug("Exec: %s", cmd_str_redacted)

        proc = None
        try:
            proc = subprocess.Popen(  # noqa: S603 (fixed argv (allowlisted tool or helper); no shell)
                final_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            stdout, stderr = proc.communicate(timeout=timeout)

            log_msg = f"Return: {proc.returncode}"
            if stdout:
                log_msg += (
                    f" | Stdout: {stdout.strip()[:200]}..."
                    if len(stdout) > 200
                    else f" | Stdout: {stdout.strip()}"
                )
            if stderr:
                log_msg += (
                    f" | Stderr: {stderr.strip()[:200]}..."
                    if len(stderr) > 200
                    else f" | Stderr: {stderr.strip()}"
                )
            logger.debug(log_msg)

            if proc.returncode in (126, 127) and require_root:
                stderr_lower = (stderr or "").lower()
                if "dismissed" in stderr_lower:
                    logger.warning(
                        "Privilege elevation cancelled by user for: %s",
                        cmd_str_redacted,
                    )
                    return CommandResult(
                        False, 126, "", "Authentication cancelled by user", final_cmd
                    )
                if proc.returncode == 127 and "not found" in stderr_lower:  # sf-str: allow pkexec error string, low-risk
                    return CommandResult(False, 127, "", stderr.strip(), final_cmd)

            return CommandResult(
                success=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=(stdout or "").strip(),
                stderr=(stderr or "").strip(),
                command=final_cmd,
            )
        except subprocess.TimeoutExpired:
            logger.error("Timeout (%ss) executing: %s", timeout, cmd_str_redacted)
            if proc is not None:
                CommandRunner._terminate_process_group(proc)
            return CommandResult(False, -1, "", f"Timeout ({timeout}s) exceeded", final_cmd)
        except Exception as e:
            logger.exception("Exception executing: %s", cmd_str_redacted)
            return CommandResult(False, -1, "", str(e), final_cmd)

    @staticmethod
    def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
        # M2 note: after pkexec setuid(0) the user-owned daemon gets EPERM
        # signalling the root child. That is expected — the helper enforces
        # the real deadline via killpg on its own (same-euid) children.
        # Here we attempt cleanup best-effort and never raise.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=3)
        except PermissionError as exc:
            logger.warning(
                "Cannot signal elevated child (EPERM after pkexec setuid); "
                "helper-side deadline owns enforcement: %s",
                exc,
            )
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=2)
            except Exception:  # noqa: S110 (best-effort wait after SIGKILL; proc already dead or reaped)
                pass
        except Exception:
            logger.debug("Failed to terminate process group cleanly", exc_info=True)

    @staticmethod
    def is_service_active(service_name: str) -> bool:
        res = CommandRunner.run(
            ["systemctl", "is-active", "--quiet", service_name],
            timeout=5.0,
        )
        return res.success
