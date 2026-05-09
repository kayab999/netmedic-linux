import subprocess
import json
import logging

def get_network_snapshot():
    """
    Recolecta el estado de red usando herramientas nativas de Linux.
    Retorna un JSON ultra-denso para el consumo del Piloto Automático.
    """
    snapshot = {
        "ifaces": {},
        "dns": [],
        "vpn": {"active": False, "provider": "none"},
        "latency_ms": 0,
        "internet": False
    }

    # 1. Interfaces (usando ip -j)
    try:
        iface_data = json.loads(subprocess.check_output(["ip", "-j", "link"]).decode())
        for iface in iface_data:
            snapshot["ifaces"][iface["ifname"]] = iface.get("operstate", "unknown")
    except Exception as e:
        logging.error(f"Error recolectando interfaces: {e}")

    # 2. DNS (leer /etc/resolv.conf)
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if line.startswith("nameserver"):
                    snapshot["dns"].append(line.split()[1])
    except:
        pass

    # 3. Latencia (ping rápido)
    try:
        ping_res = subprocess.run(["ping", "-c", "1", "-W", "1", "8.8.8.8"], capture_output=True)
        if ping_res.returncode == 0:
            snapshot["internet"] = True
            # Extraer tiempo de ping (simplificado)
            output = ping_res.stdout.decode()
            time_part = output.split("time=")[1].split(" ms")[0]
            snapshot["latency_ms"] = float(time_part)
    except:
        pass

    return snapshot
