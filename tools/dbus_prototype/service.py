"""Prototype D-Bus helper service (v2.0 design track, NOT shipped).

Implements docs/DBUS_DESIGN.md §3 on top of the existing, reviewed
machinery: plan_verb validation, ActionSpec→polkit_id mapping, and
execute_plan execution (staging, killpg deadlines, journal records).

Bus transport (Gio registration, name ownership, subject extraction)
sits behind the Authority seam so unit tests run without a system bus.
Only resolve→authorize→execute is security-critical; the rest is reuse.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

BUS_NAME = "com.kayab.netmedic"
OBJECT_PATH = "/com/kayab/netmedic/Helper"
INTERFACE = "com.kayab.netmedic.Helper1"


@dataclass(frozen=True)
class CallerSubject:
    """Bus-attested caller identity (never caller-supplied strings)."""

    unique_name: str
    pid: int
    uid: int
    unit: Optional[str] = None


class Authority(Protocol):
    """Polkit authority seam (production impl uses Gio; tests use Fake)."""

    def check(self, subject: CallerSubject, action_id: str,
              allow_interaction: bool) -> bool:
        ...


class FakeAuthority:
    """Test double: allows exactly the configured action IDs, records calls."""

    def __init__(self, allowed: frozenset[str] = frozenset()) -> None:
        self.allowed = allowed
        self.calls: List[tuple[str, str]] = []

    def check(self, subject: CallerSubject, action_id: str,
              allow_interaction: bool) -> bool:
        self.calls.append((subject.unique_name, action_id))
        return action_id in self.allowed


try:
    from gi.repository import Gio  # noqa: F401 (vehicle probe)

    _GIO_AVAILABLE = True
except ImportError:  # pragma: no cover - minimal envs without PyGObject
    _GIO_AVAILABLE = False


class GioAuthority:
    """Production authority (v2.0 build track wires the Gio proxy here)."""

    def __init__(self, bus: Any = None) -> None:
        if not _GIO_AVAILABLE:
            raise ImportError("PyGObject (Gio) is required for the bus authority")
        self._bus = bus

    def check(self, subject: CallerSubject, action_id: str,
              allow_interaction: bool) -> bool:
        # Build a proxy for org.freedesktop.PolicyKit1.Authority and call
        # CheckAuthorization with the subject's UnixProcess + unit details.
        raise NotImplementedError("v2.0 build track: wire Gio proxy here")


class HelperService:
    """The §3 flow: validate → resolve → authorize → execute."""

    def __init__(self, authority: Authority,
                 on_result: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        self._authority = authority
        self._on_result = on_result

    def execute(self, verb: str, args_json: str,
                subject: CallerSubject) -> Dict[str, Any]:
        """Single D-Bus method: Execute(verb, args_json)."""
        from netmedic.action_catalog import ACTIONS
        from netmedic.helper_verbs import VerbValidationError, plan_verb

        try:
            args = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError as exc:
            return {"ok": False, "message": f"Invalid args JSON: {exc}"}
        if not isinstance(args, dict):
            return {"ok": False, "message": "args must be a JSON object"}

        # 1. Validate first: malformed verbs never spend an auth decision.
        try:
            plan = plan_verb(verb, args)
        except VerbValidationError as exc:
            return {"ok": False, "message": str(exc)}

        # 2. Resolve the VALIDATED verb to exactly one polkit action.
        # Shared verbs (vpn-run-script serves 3 operations today) are
        # ambiguous by construction and must be denied: the v2.0 build
        # track requires the M8b verb split first. See docs/DBUS_DESIGN.md.
        matches = [s for s in ACTIONS if s.helper_verb == verb]
        if len(matches) != 1 or matches[0].polkit_id is None:
            return {"ok": False,
                    "message": f"Verb has no unique polkit action: {verb}"}

        # 3. Authorize the ATTESTED subject (never caller strings).
        try:
            allowed = self._authority.check(subject, matches[0].polkit_id, True)
        except Exception as exc:
            logger.exception("authority check failed")
            return {"ok": False, "message": f"Authorization error: {exc}"}
        if not allowed:
            denied = {"ok": False, "message": f"Denied: {matches[0].polkit_id}"}
            self._emit(verb, denied)
            return denied

        # 4. Execute with the existing, reviewed machinery.
        from netmedic.helper_main import execute_plan
        result = execute_plan(plan)
        self._emit(verb, result)
        return result

    def _emit(self, verb: str, result: Dict[str, Any]) -> None:
        if self._on_result is not None:
            try:
                self._on_result(verb, result)
            except Exception:
                logger.debug("result hook failed", exc_info=True)
