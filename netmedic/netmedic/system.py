import json
import logging
import os
import re
import signal
import subprocess
import shutil
from typing import Any, FrozenSet, List, Mapping, Optional

from netmedic.models import CommandResult
from netmedic.config import Config
from netmedic.helper_verbs import VerbValidationError, plan_verb

logger = logging.getLogger(__name__)

# Basenames allowed under require_root=True. Path is resolved via shutil.which
# or absolute path; argv shape is still caller-controlled within these tools.
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
    "bash",
    "sh",
})


class CommandRunner:
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
    def _helper_invocation(verb: str, args: Mapping[str, Any], *, timeout: Optional[int]) -> List[str]:
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
            pkexec = shutil.which("pkexec")
            if not pkexec:
                raise FileNotFoundError("pkexec not found")
            return [pkexec] + base
        return base

    @staticmethod
    def run_elevated(
        verb: str,
        args: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """Run a fixed helper verb, or expand to legacy argv when helper is off.

        Opt-in: NETMEDIC_USE_HELPER=1 → pkexec netmedic-helper <verb> --json ...
        Default: plan_verb() → execute first/only command chain via legacy run().
        """
        if timeout is None:
            timeout = Config.get_default_timeout()
        args = dict(args or {})

        try:
            plan = plan_verb(verb, args)
        except VerbValidationError as exc:
            return CommandResult(False, 2, "", str(exc), [verb])

        if Config.use_privileged_helper():
            try:
                final_cmd = CommandRunner._helper_invocation(verb, args, timeout=timeout)
            except FileNotFoundError as exc:
                return CommandResult(False, 127, "", str(exc), [verb])
            # Helper already elevates; do not double-wrap with require_root.
            result = CommandRunner.run(final_cmd, require_root=False, timeout=timeout)
            # Prefer helper JSON message when present.
            if result.stdout:
                try:
                    payload = json.loads(result.stdout.splitlines()[-1])
                    if isinstance(payload, dict) and "message" in payload:
                        msg = str(payload["message"])
                        ok = bool(payload.get("ok", result.success))
                        return CommandResult(
                            ok,
                            0 if ok else result.returncode,
                            result.stdout,
                            "" if ok else msg,
                            result.command,
                        )
                except json.JSONDecodeError:
                    pass
            return result

        # Legacy path: run planned argv sequence with require_root.
        last = CommandResult(False, -1, "", "No commands planned", [verb])
        for argv in plan.commands:
            if argv and argv[0] == "__vpn_script__":
                # Reconstruct env + script for legacy elevation.
                script = argv[1]
                env_pairs = argv[3:]
                legacy = ["env", *env_pairs, script]
                last = CommandRunner.run(legacy, require_root=True, timeout=timeout)
            else:
                last = CommandRunner.run(argv, require_root=True, timeout=timeout)
            if not last.success:
                return last
        return last

    @staticmethod
    def run(
        command: List[str],
        require_root: bool = False,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """
        Execute commands with timeout, optional elevation, and sanitized logging.
        """
        if timeout is None:
            timeout = Config.get_default_timeout()

        final_cmd = list(command)

        if require_root and os.geteuid() != 0:
            allow_err = CommandRunner._assert_root_command_allowed(final_cmd)
            if allow_err:
                logger.error(allow_err)
                return CommandResult(False, 126, "", allow_err, final_cmd)
            if not shutil.which("pkexec"):
                logger.error("pkexec not found, cannot elevate privileges")
                return CommandResult(False, 127, "", "pkexec not found", final_cmd)
            final_cmd = ["pkexec"] + final_cmd

        cmd_str_redacted = CommandRunner._redact_command(final_cmd)
        logger.debug("Exec: %s", cmd_str_redacted)

        proc = None
        try:
            proc = subprocess.Popen(
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
                if proc.returncode == 127 and "not found" in stderr_lower:
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
    def _terminate_process_group(proc: subprocess.Popen) -> None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
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
