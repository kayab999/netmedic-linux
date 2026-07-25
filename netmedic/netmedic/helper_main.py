"""CLI entry for netmedic-helper (Phase B prototype).

Usage:
  netmedic-helper <verb> [--dry-run] [--json '{...}']
  netmedic-helper --list-verbs

Dry-run (default when not root and NETMEDIC_HELPER_EXECUTE is unset) prints the
planned argv sequence as JSON without running commands. Execute mode runs the
planned commands with subprocess (intended under pkexec as root).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence

from netmedic.helper_verbs import (
    ALL_VERBS,
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


def _should_execute(explicit_execute: bool, dry_run: bool) -> bool:
    if dry_run:
        return False
    if explicit_execute:
        return True
    # Default: execute only when already root (pkexec path) or env forces it.
    if os.environ.get("NETMEDIC_HELPER_EXECUTE", "").lower() in ("1", "true", "yes"):
        return True
    return os.geteuid() == 0


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_argv(argv: List[str], timeout: Optional[int]) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout or 60,
        check=False,
        start_new_session=True,
    )


def _execute_vpn_script(marker_cmd: List[str], timeout: Optional[int]) -> Dict[str, Any]:
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
    try:
        actual = _hash_file(script)
    except OSError as exc:
        return {"ok": False, "message": f"Cannot read script: {exc}", "details": None}
    if actual != expected:
        return {
            "ok": False,
            "message": "Security abort: Script integrity failure.",
            "details": f"expected {expected}, got {actual}",
        }
    cmd = ["env", *env_pairs, script]
    try:
        proc = _run_argv(cmd, timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"Timeout ({timeout}s) exceeded", "details": None}
    if proc.returncode == 0:
        return {
            "ok": True,
            "message": "VPN script completed",
            "details": (proc.stdout or "").strip()[:500] or None,
        }
    err = (proc.stderr or proc.stdout or "").strip()
    if "dismissed" in err.lower():
        return {"ok": False, "message": "Authentication cancelled by user", "details": err}
    return {
        "ok": False,
        "message": err or f"VPN script failed (exit {proc.returncode})",
        "details": None,
    }


def execute_plan(plan: VerbPlan, *, timeout: Optional[int] = None) -> Dict[str, Any]:
    """Run planned commands; return helper JSON payload."""
    outputs: List[str] = []
    for argv in plan.commands:
        if argv and argv[0] == "__vpn_script__":
            return _execute_vpn_script(argv, timeout)
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
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

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
    if "integrity" in message or "security abort" in message:
        return _emit(result, EXIT_INTEGRITY)
    if "cancel" in message or "dismissed" in message:
        return _emit(result, EXIT_CANCELLED)
    return _emit(result, EXIT_OP_FAIL)


if __name__ == "__main__":
    sys.exit(main())
