import os
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.getcwd())

from netmedic.network import NetworkMedic
from netmedic.config import Config

def test_persistence():
    medic = NetworkMedic()
    # Mock adding an interface
    medic._created_ifaces.add("testif0")
    medic._save_state()
    
    print(f"State file: {medic._state_file}")
    with open(medic._state_file, "r") as f:
        print(f"Content: {f.read()}")
    
    # Re-instantiate (it's a singleton, so we need to reset it for testing or just check logic)
    # Since it's a singleton, __init__ only runs once.
    # Let's manually trigger __init__ logic or check if _load_state works.
    medic._created_ifaces = set()
    medic._load_state()
    print(f"Loaded interfaces: {medic._created_ifaces}")
    assert "testif0" in medic._created_ifaces
    print("Persistence test passed!")

if __name__ == "__main__":
    test_persistence()
