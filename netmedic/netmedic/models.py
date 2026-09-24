import warnings
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Any


class ResultCode(str, Enum):
    """Structured business result code. display (message) is separate."""
    OK = "ok"              # executed AND verified (post-condition passed)
    EXECUTED = "executed"  # exit 0, no post-condition yet
    PARTIAL = "partial"    # partially verified (e.g. DNS ok WAN fail)
    FAILED = "failed"      # verified failure (post-condition failed)
    SKIPPED = "skipped"    # not executed, precondition missing
    ERROR = "error"        # operational error / exception
    CANCELLED = "cancelled"  # user cancelled auth


@dataclass(frozen=True)
class CommandResult:
    """Captura fiel de la ejecución de un subproceso."""
    success: bool
    returncode: int
    stdout: str
    stderr: str
    command: List[str]

@dataclass(frozen=True)
class NetResult:
    """Resultado de negocio para la UI. message is display-only; code is source of truth."""
    operation: str
    success: bool
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Optional[Any] = None
    data: Any = None
    code: Optional["ResultCode"] = None

    def __post_init__(self) -> None:
        # Derive code from success if not explicitly set (backward compat).
        # Use direct dict access to avoid triggering deprecation warning during init
        success_val = object.__getattribute__(self, "success")
        code_val = object.__getattribute__(self, "code")
        if code_val is None:
            inferred = ResultCode.OK if success_val else ResultCode.FAILED
            object.__setattr__(self, "code", inferred)
        else:
            # Normalize string to enum if needed (IPC deserialization)
            if isinstance(code_val, str):
                try:
                    object.__setattr__(self, "code", ResultCode(code_val))
                except ValueError:
                    object.__setattr__(self, "code", ResultCode.FAILED)
        # Keep success consistent with code when code explicitly indicates failure/cancel
        # but do not override explicit success for EXECUTED/PARTIAL which are still "executed"
        # success remains as passed for backward compat; icon comes from code.

    def __getattribute__(self, name: str) -> Any:
        if name == "success":
            # Emit deprecation outside try that would swallow error-warnings
            try:
                current = inspect.currentframe()
                frame = current.f_back if current is not None else None
                filename = frame.f_code.co_filename if frame is not None and frame.f_code else ""
                should_warn = True
                if "models.py" in filename:
                    should_warn = False
                elif "tests" in filename:
                    should_warn = False
                else:
                    try:
                        info = inspect.getframeinfo(frame) if frame else None
                        line = "".join(info.code_context or []) if info and info.code_context else ""
                        if "sf-success: allow" in line.lower():
                            should_warn = False
                    except Exception:
                        should_warn = True
                if should_warn:
                    warnings.warn("NetResult.success is deprecated, use code (ResultCode)", UserWarning, stacklevel=2)
            except Warning:
                raise
            except Exception:
                pass
        return object.__getattribute__(self, name)

    def to_log_entry(self) -> str:
        local_time = self.timestamp.astimezone()
        # Icon maps from code, not success, so EXECUTED shows ⚠️
        code = self.code if isinstance(self.code, ResultCode) else ResultCode(self.code) if isinstance(self.code, str) else None
        if code == ResultCode.OK:
            icon = "✅"
        elif code in (ResultCode.EXECUTED, ResultCode.PARTIAL):
            icon = "⚠️"
        elif code == ResultCode.SKIPPED:
            icon = "⏭️"
        elif code == ResultCode.CANCELLED:
            icon = "⚠️"
        elif code in (ResultCode.FAILED, ResultCode.ERROR):
            icon = "❌"
        else:
            icon = "✅" if self.success else "❌"
        return f"[{local_time.strftime('%H:%M:%S')}] {icon} {self.operation}: {self.message}"

@dataclass
class TaskResult:
    """Contenedor agnóstico para resultados de hilos."""
    success: bool
    data: Optional[Any] = None  # Usualmente NetResult
    error: Optional[str] = None
    traceback: Optional[str] = None
