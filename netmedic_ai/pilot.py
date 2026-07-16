import hashlib
import json
import logging
import re
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

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "nandi-mini-tool-calling.gguf"
SUM_PATH = BASE_DIR / "nandi-mini-tool-calling.sum"

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
        self._initialize_model()

    def _verify_model_integrity(self):
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
        state_str = json.dumps(network_state)
        prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"State: {state_str}\n"
            f"Request: {sanitized_request}\n"
            "Decision:"
        )

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

    def process_event(self, network_state: dict, user_request: str) -> dict:
        decision = self.infer_intent(network_state, user_request)
        if decision.get("status") == "error":
            return decision
        return PilotoGuardrail.execute_tool(
            decision["action"],
            decision.get("params", {}),
        )


def _get_pilot() -> NandiPilot:
    global _pilot_instance
    if _pilot_instance is None:
        _pilot_instance = NandiPilot()
    return _pilot_instance


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