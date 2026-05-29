import subprocess
import time
import os
import signal
from pathlib import Path

STATE_DIR = Path("/home/carlos/.local/state/netmedic")

def test_crash_resilience():
    print("Iniciando prueba de resiliencia: Crash test simulado...")
    
    # 1. Iniciar app en headless
    process = subprocess.Popen(["python3", "-m", "netmedic.app", "--headless"], cwd="netmedic", env={**os.environ, "PYTHONPATH": "."})
    time.sleep(2)
    
    # 2. Verificar archivos creados
    if not (STATE_DIR / "ipc.pid").exists():
        print("Error: PID file no creado.")
        process.terminate()
        return

    # 3. Simular crash (SIGKILL - no deja cleanup)
    print("Simulando crash violento (SIGKILL)...")
    process.kill()
    process.wait()
    
    # 4. Verificar limpieza (Esperamos que el próximo inicio limpie si el anterior falló)
    # Nota: Si el crash es violento, los archivos quedan.
    # El test debe verificar que la app pueda arrancar de nuevo.
    
    print("Verificando recuperación tras crash...")
    process2 = subprocess.Popen(["python3", "-m", "netmedic.app", "--headless"], cwd="netmedic", env={**os.environ, "PYTHONPATH": "."})
    time.sleep(2)
    
    if process2.poll() is None:
        print("Recuperación exitosa.")
        process2.terminate()
    else:
        print("Error: App no pudo arrancar tras crash.")

if __name__ == "__main__":
    test_crash_resilience()
