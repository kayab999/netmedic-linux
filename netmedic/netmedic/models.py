from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Any

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
    """Resultado de negocio para la UI."""
    operation: str
    success: bool
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Optional[str] = None
    
    def to_log_entry(self) -> str:
        local_time = self.timestamp.astimezone()
        icon = "✅" if self.success else "❌"
        return f"[{local_time.strftime('%H:%M:%S')}] {icon} {self.operation}: {self.message}"

@dataclass
class TaskResult:
    """Contenedor agnóstico para resultados de hilos."""
    success: bool
    data: Optional[Any] = None  # Usualmente NetResult
    error: Optional[str] = None
    traceback: Optional[str] = None
