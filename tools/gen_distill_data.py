import json
import random

def generate_dataset(num_entries=1000):
    dataset = []
    
    scenarios = [
        {
            "action": "run_speedtest",
            "template": "Comprueba la velocidad de mi conexión.",
            "params": {}
        },
        {
            "action": "refresh_network_identity",
            "template": "Quiero ser anónimo, refresca mi identidad de red.",
            "params": {"mac_randomization": True}
        },
        {
            "action": "configure_local_vpn",
            "template": "Configura el perfil de VPN en {path}.",
            "params_gen": lambda: {"profile_path": f"/etc/openvpn/{random.choice(['netflix', 'work', 'privacy', 'gaming'])}.ovpn"}
        },
        {
            "action": "configure_firewall",
            "template": "Abre el puerto {port} para {proto}.",
            "params_gen": lambda: {"action": "allow", "port": random.choice([80, 443, 8080, 22, 53]), "protocol": random.choice(["tcp", "udp"])}
        }
    ]

    for _ in range(num_entries):
        sc = random.choice(scenarios)
        params = sc["params_gen"]() if "params_gen" in sc else sc["params"]
        
        # Inyectar variables en la plantilla si es necesario
        instruction = sc["template"]
        if "{path}" in instruction:
            instruction = instruction.replace("{path}", params["profile_path"])
        if "{port}" in instruction:
            instruction = instruction.replace("{port}", str(params["port"]))
            instruction = instruction.replace("{proto}", params["protocol"])

        entry = {
            "instruction": instruction,
            "output": json.dumps({"action": sc["action"], "params": params})
        }
        dataset.append(entry)

    with open("kayab_distill_dataset.json", "w") as f:
        json.dump(dataset, f, indent=2)
    print(f"Dataset generado con {num_entries} ejemplos en kayab_distill_dataset.json")

if __name__ == "__main__":
    generate_dataset()
