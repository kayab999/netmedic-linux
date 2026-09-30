import hashlib
import json
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama, LlamaGrammar
except ImportError:  # pragma: no cover - optional AI dependency
    Llama = None
    LlamaGrammar = None

from netmedic_ai.guardrail import PilotoGuardrail
from netmedic_ai.toolkit import registry

MODEL_FILENAME = "nandi-mini-tool-calling.gguf"
SUM_FILENAME = "nandi-mini-tool-calling.sum"


def _resolve_asset_dir() -> Path:
    """Locate the directory holding the model + checksum (M5).

    Order: explicit admin override → installed package data → PyInstaller
    bundle → repo-checkout legacy layout. The old single
    ``Path(__file__).parent.parent`` broke for installed packages and the
    PyInstaller binary, whose layout differs from a git checkout.
    """
    override = os.environ.get("NETMEDIC_AI_MODEL_DIR")
    if override:
        return Path(override)
    try:
        from importlib.resources import files as _res_files

        pkg_data = _res_files("netmedic_ai")
        if (pkg_data / MODEL_FILENAME).is_file():
            return Path(str(pkg_data))
    except Exception:  # noqa: S110 (optional package-data probe; falls through to _MEIPASS/checkout)
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and Path(meipass, MODEL_FILENAME).is_file():
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


BASE_DIR = _resolve_asset_dir()
MODEL_PATH = BASE_DIR / MODEL_FILENAME
SUM_PATH = BASE_DIR / SUM_FILENAME

SYSTEM_PROMPT = (
    "You are the NetMedic Autopilot.\n"
    "Your purpose is maintaining network integrity.\n"
    "- You may only perform actions via the ActionRegistry.\n"
    "- NEVER attempt to execute shell commands directly.\n"
    "- Prioritize user stability and safety."
)

_GBNF_TEMPLATE = (
    'root ::= object\n'
    "action_val ::= {ACTION_PLACEHOLDER}\n"
    'object ::= "{" ws "\\"action\\": " action_val "," ws "\\"params\\": " params "}" ws\n'
    'params ::= "{" ws "}" ws | "{" ws pair (ws "," ws pair)* ws "}" ws\n'
    'pair ::= string ":" ws string\n'
    'string ::= "\\"" ([^"\\\\] | "\\\\" ["\\\\/bfnrt] | "\\\\" "u" [0-9a-fA-F]{4})* "\\""\n'
    "ws ::= [ \\t\\n\\r]*\n"
)

_pilot_instance: Optional["NandiPilot"] = None


class NandiPilot:
    def __init__(self):
        self._verify_model_integrity()
        self.manifest = registry.get_manifest()
        self.grammar = None
        self.llm = None
        # M5: llama_cpp.Llama is not thread-safe and the 950 MB model must
        # load once — instance lock serializes inference across the IPC
        # workers sharing this pilot.
        self._infer_lock = threading.Lock()
        self._initialize_model()

    def _verify_model_integrity(self):
        # M5 note: the .sum detects corruption, not tampering — both files
        # live side by side and are only as trustworthy as their directory.
        # Strict setups should point NETMEDIC_AI_MODEL_DIR at read-only,
        # admin-owned media and verify provenance out of band.
        if not MODEL_PATH.exists() or not SUM_PATH.exists():
            raise FileNotFoundError(f"Missing Model/Sum at {MODEL_PATH}")

        with open(SUM_PATH, "r", encoding="utf-8") as f:
            expected_hash = f.read().strip()

        sha256_hash = hashlib.sha256()
        with open(MODEL_PATH, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        if sha256_hash.hexdigest() != expected_hash:
            raise ValueError("INTEGRITY_VIOLATION: The GGUF file has been altered.")

    @staticmethod
    def _sanitize_input(text: str) -> str:
        return re.sub(r"[\x00-\x1f\x7f]", "", text)[:500]

    # M5 prompt-injection/context budget: SSIDs, hostnames and probe
    # strings are attacker-influenced, so the state block gets the same
    # control-char stripping as user_request plus hard size caps. With
    # n_ctx=2048 and max_tokens=128, state (1500) + request (500) + system
    # prompt (~120) + grammar can no longer overflow the window.
    _MAX_STATE_CHARS = 1500
    _MAX_STATE_KEYS = 64
    _MAX_STATE_STR = 120

    @classmethod
    def _sanitize_state(cls, network_state: object) -> str:
        """Deterministic, bounded, control-char-free JSON of *network_state*."""
        if not isinstance(network_state, dict):
            return "{}"
        clean: Dict[str, Any] = {}
        for key in sorted(network_state):
            if len(clean) >= cls._MAX_STATE_KEYS:
                break
            value = network_state[key]
            clean[str(key)[:64]] = cls._scrub_value(value)
        text = json.dumps(clean, sort_keys=True, ensure_ascii=True, default=str)
        if len(text) > cls._MAX_STATE_CHARS:
            text = text[: cls._MAX_STATE_CHARS] + '..."truncated":true}'
        return text

    @classmethod
    def _scrub_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            return re.sub(r"[\x00-\x1f\x7f]", "", value)[: cls._MAX_STATE_STR]
        if isinstance(value, dict):
            return {str(k)[:64]: cls._scrub_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._scrub_value(v) for v in value[:32]]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return str(value)[: cls._MAX_STATE_STR]

    def _initialize_model(self):
        if Llama is None or LlamaGrammar is None:
            raise ImportError(
                "llama-cpp-python is not installed. Install with: pip install .[ai]"
            )

        action_list = " | ".join(f'"{tool["name"]}"' for tool in self.manifest)
        gbnf = _GBNF_TEMPLATE.replace("{ACTION_PLACEHOLDER}", action_list)
        self.grammar = LlamaGrammar.from_string(gbnf)
        self.llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=2048,
            n_gpu_layers=-1,
            verbose=False,
        )

    def infer_intent(self, network_state: dict, user_request: str) -> Dict[str, Any]:
        """Returns the LLM decision without executing the tool."""
        sanitized_request = self._sanitize_input(user_request)
        state_str = self._sanitize_state(network_state)
        prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"State: {state_str}\n"
            f"Request: {sanitized_request}\n"
            "Decision:"
        )

        with self._infer_lock:
            response = self.llm(
                prompt,
                grammar=self.grammar,
                max_tokens=128,
            )
        decision = json.loads(response["choices"][0]["text"])
        return {
            "status": "ok",
            "action": decision["action"],
            "params": decision.get("params", {}),
        }

    def process_event(
        self,
        network_state: dict,
        user_request: str,
        *,
        confirmed: bool = False,
    ) -> dict:
        """Infer intent and optionally execute — execution requires confirmed=True.

        Prefer interpret_intent / IPC user_intent for preview, then a separate
        confirmed privileged IPC call. Auto-execute without confirmation is forbidden.
        """
        decision = self.infer_intent(network_state, user_request)
        if decision.get("status") == "error":
            return decision
        if not confirmed:
            return {
                "status": "error",
                "message": (
                    "process_event refuses unconfirmed execution. "
                    "Use interpret_intent for preview, then a confirmed IPC action."
                ),
                "requires_confirmation": True,
                "action": decision.get("action"),
                "params": decision.get("params", {}),
            }
        return PilotoGuardrail.execute_tool(
            decision["action"],
            decision.get("params", {}),
        )


# M5: guards double-checked creation — without it, 4 IPC workers racing
# first use could load the 950 MB model twice.
_pilot_lock = threading.Lock()


def _get_pilot() -> NandiPilot:
    global _pilot_instance
    if _pilot_instance is None:
        with _pilot_lock:
            if _pilot_instance is None:
                _pilot_instance = NandiPilot()
    return _pilot_instance


def _reset_pilot_for_tests() -> None:
    """Test hook: drop the cached instance (tests only)."""
    global _pilot_instance
    with _pilot_lock:
        _pilot_instance = None


def interpret_intent(user_request: str, network_state: dict) -> Dict[str, Any]:
    """Module-level entry point used by the IPC action dispatcher."""
    try:
        return _get_pilot().infer_intent(network_state, user_request)
    except ImportError as exc:
        return {"status": "error", "message": str(exc)}
    except FileNotFoundError as exc:
        return {"status": "error", "message": str(exc)}
    except ValueError as exc:
        logger.error("Model integrity check failed: %s", exc)
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.exception("AI intent interpretation failed")
        return {"status": "error", "message": str(exc)}