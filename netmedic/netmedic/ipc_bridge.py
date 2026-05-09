import os
import socket
import json
import threading
import logging

# Cumplimiento estricto de estándares XDG para el estado
STATE_DIR = os.path.expanduser("~/.local/state/netmedic")
SOCK_FILE = os.path.join(STATE_DIR, "ipc.sock")
PID_FILE = os.path.join(STATE_DIR, "ipc.pid")

class NetMedicIPCServer:
    def __init__(self, action_dispatcher):
        self.sock_file = SOCK_FILE
        self.pid_file = PID_FILE
        self.action_dispatcher = action_dispatcher
        self.running = False

    def _is_process_alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def start(self):
        # 1. Validar instancia previa mediante PID file
        if os.path.exists(self.pid_file):
            with open(self.pid_file, 'r') as f:
                try:
                    pid = int(f.read().strip())
                    if self._is_process_alive(pid):
                        raise RuntimeError(f"NetMedic ya corriendo con PID {pid}")
                except ValueError:
                    pass
            os.remove(self.pid_file)

        # 2. Limpiar socket huérfano si existe
        if os.path.exists(self.sock_file):
            os.remove(self.sock_file)

        os.makedirs(STATE_DIR, exist_ok=True)

        # 3. Inicializar y hacer bind del socket ANTES de escribir el PID
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.sock_file)
        os.chmod(self.sock_file, 0o600)

        # 4. Solo ahora que bind() fue exitoso, registrar el PID
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        os.chmod(self.pid_file, 0o600)

        self.server.listen(1)
        self.running = True
        
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logging.info(f"IPC Server en línea. Escuchando en {self.sock_file}")

    def _listen_loop(self):
        while self.running:
            try:
                # Timeout para que el bucle pueda verificar self.running y cerrar limpiamente
                self.server.settimeout(1.0) 
                try:
                    conn, _ = self.server.accept()
                except socket.timeout:
                    continue

                with conn:
                    data = conn.recv(4096)
                    if data:
                        self._handle_connection(conn, data)
            except Exception as e:
                if self.running:
                    logging.error(f"Fallo en loop IPC: {e}")

    def _handle_connection(self, conn, data):
        try:
            payload = json.loads(data.decode('utf-8'))
            
            # Esperamos que payload tenga {"action": "...", "params": {...}}
            action = payload.get("action")
            params = payload.get("params", {})
            
            # Ejecutar a través del dispatcher
            result = self.action_dispatcher(action, params)
            response = json.dumps(result)
            
        except json.JSONDecodeError:
            response = json.dumps({"status": "error", "message": "Payload JSON inválido."})
        except Exception as e:
            response = json.dumps({"status": "error", "message": f"Fallo interno del IPC: {str(e)}"})
        
        conn.sendall(response.encode('utf-8'))

    def stop(self):
        """Cierre seguro del socket durante el cleanup() de NetMedic."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.server:
            self.server.close()
        if os.path.exists(self.sock_file):
            os.remove(self.sock_file)
        logging.info("IPC Server detenido y socket limpiado.")
