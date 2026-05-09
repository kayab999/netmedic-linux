from netmedic_ai.pilot import NandiPilot
import json

def run_oracle_test():
    print("Iniciando Oracle Test de Inferencia...")
    pilot = NandiPilot()
    
    test_cases = [
        {
            "name": "VPN Degradada",
            "state": {"ifaces": {"tun0": "up"}, "latency_ms": 487, "vpn": {"active": True}, "internet": True, "dns": ["8.8.8.8"]},
            "request": "La red va muy lenta.",
            "expected_action": "vpn_reconnect"
        },
        {
            "name": "VPN Caída (No reconectar)",
            "state": {"ifaces": {"tun0": "down"}, "latency_ms": 12, "vpn": {"active": False}, "internet": True, "dns": ["1.1.1.1"]},
            "request": "La red va muy lenta.",
            "expected_action": "network_status"
        },
        {
            "name": "Test Velocidad",
            "state": {"ifaces": {"wlan0": "up"}, "latency_ms": 80, "internet": True, "dns": ["1.1.1.1"]},
            "request": "¿Qué velocidad tengo?",
            "expected_action": "run_speedtest"
        }
    ]

    for case in test_cases:
        print(f"\n--- Caso: {case['name']} ---")
        try:
            result = pilot.process_event(case["state"], case["request"])
            action = result.get("action")
            print(f"Request: {case['request']}")
            print(f"Decisión: {action}")
            if action == case["expected_action"]:
                print("✅ PASSED")
            else:
                print(f"❌ FAILED (Esperado: {case['expected_action']})")
        except Exception as e:
            print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    run_oracle_test()
