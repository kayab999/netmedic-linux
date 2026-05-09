import hashlib
import os
import json
import re
from pathlib import Path
from llama_cpp import Llama, LlamaGrammar
from .toolkit import registry
from .guardrail import PilotoGuardrail

# Path persistente relativo a la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "nandi-mini-tool-calling.gguf"
SUM_PATH = BASE_DIR / "nandi-mini-tool-calling.sum"

SYSTEM_PROMPT = """Eres el Piloto Automático de NetMedic.
Tu propósito es el mantenimiento de la integridad de la red.
- Solo puedes realizar acciones mediante el ActionRegistry.
- NUNCA intentes ejecutar comandos shell directamente.
- Prioriza la estabilidad y seguridad del usuario."""

class NandiPilot:
    def __init__(self):
        self._verify_model_integrity()
        self.manifest = registry.get_manifest()
        self._initialize_model()

    def _verify_model_integrity(self):
        """Bloqueo de seguridad si el modelo no coincide con el hash esperado."""
        if not MODEL_PATH.exists() or not SUM_PATH.exists():
            raise FileNotFoundError(f"Missing Model/Sum at {MODEL_PATH}")
            
        with open(SUM_PATH, 'r') as f:
            expected_hash = f.read().strip()
            
        sha256_hash = hashlib.sha256()
        with open(MODEL_PATH, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
                
        if sha256_hash.hexdigest() != expected_hash:
            raise ValueError("INTEGRITY_VIOLATION: The GGUF file has been altered.")

    def _sanitize_input(self, text):
        return re.sub(r'[\x00-\x1f\x7f]', '', text)[:500]

# Constante estática — raw string, sin f-string, sintaxis GBNF pura
_GBNF_TEMPLATE = r'''root ::= object
action_val ::= {ACTION_PLACEHOLDER}
object ::= "{" ws "\"action\": " action_val "," ws "\"params\": " params "}" ws
params ::= "{" ws "}" ws | "{" ws pair (ws "," ws pair)* ws "}" ws
pair ::= string ":" ws string
string ::= "\"" ([^"\\] | "\\" ["\\/bfnrt] | "\\" "u" [0-9a-fA-F]{4})* "\""
ws ::= [ \t\n\r]*
'''

class NandiPilot:
    def __init__(self):
        self._verify_model_integrity()
        self.manifest = registry.get_manifest()
        self._initialize_model()

    def _verify_model_integrity(self):
        """Bloqueo de seguridad si el modelo no coincide con el hash esperado."""
        if not MODEL_PATH.exists() or not SUM_PATH.exists():
            raise FileNotFoundError(f"Missing Model/Sum at {MODEL_PATH}")
            
        with open(SUM_PATH, 'r') as f:
            expected_hash = f.read().strip()
            
        sha256_hash = hashlib.sha256()
        with open(MODEL_PATH, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
                
        if sha256_hash.hexdigest() != expected_hash:
            raise ValueError("INTEGRITY_VIOLATION: The GGUF file has been altered.")

    def _sanitize_input(self, text):
        return re.sub(r'[\x00-\x1f\x7f]', '', text)[:500]

    def _initialize_model(self):
        """Carga Nandi Mini (150M) con gramática GBNF dinámica y estrictamente tipada."""
        # La única parte dinámica: la enumeración de herramientas permitidas
        action_list = ' | '.join(f'"{t["name"]}"' for t in self.manifest)
        
        # Sustitución segura sin f-string en las partes estáticas
        gbnf = _GBNF_TEMPLATE.replace('{ACTION_PLACEHOLDER}', action_list)
        
        self.grammar = LlamaGrammar.from_string(gbnf)
        self.llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=2048,
            n_gpu_layers=-1,
            verbose=False
        )


    def process_event(self, network_state: dict, user_request: str):
        sanitized_request = self._sanitize_input(user_request)
        state_str = json.dumps(network_state)
        prompt = f"{SYSTEM_PROMPT}\nState: {state_str}\nRequest: {sanitized_request}\nDecision:"

        response = self.llm(prompt=prompt, grammar=self.grammar, max_tokens=128)
        decision = json.loads(response['choices'][0]['text'])
        
        # Ejecutar y retornar tanto decisión como ejecución
        execution_result = PilotoGuardrail.execute_tool(decision['action'], decision['params'])
        return {
            "action": decision['action'],
            "params": decision['params'],
            "execution": execution_result
        }
