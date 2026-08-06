import json
import random
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

SCENARIOS = {
    "mqtt_flood",
    "auth_failures",
    "unauthorized_topic",
    "unknown_destination",
}


def attack_events(scenario: str, *, device_id: str, intensity: int, seed: int) -> list[dict[str, object]]:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unsupported safe attack scenario: {scenario}")
    rng = random.Random(seed)
    events: list[dict[str, object]] = []
    count = intensity if scenario == "mqtt_flood" else max(3, intensity // 3)
    for _ in range(count):
        topic = f"iot/{device_id}/telemetry"
        destination = "mqtt-broker"
        auth_success = True
        size = rng.randint(800, 2500) if scenario == "mqtt_flood" else rng.randint(100, 300)
        if scenario == "auth_failures":
            auth_success = False
        if scenario == "unauthorized_topic":
            topic = f"iot/admin/{device_id}/shadow"
        if scenario == "unknown_destination":
            destination = "unknown-simulated-destination"
        events.append(
            {
                "device_id": device_id,
                "device_type": "smart_camera" if device_id.startswith("camera") else "unknown",
                "timestamp": datetime.now(UTC).isoformat(),
                "topic": topic,
                "message_size": size,
                "destination": destination,
                "auth_success": auth_success,
                "value": rng.random(),
            }
        )
    return events


def publish_attack(host: str, port: int, scenario: str, *, device_id: str, intensity: int, seed: int) -> int:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"safe-attack-{scenario}")
    client.connect(host, port, keepalive=60)
    count = 0
    for payload in attack_events(scenario, device_id=device_id, intensity=intensity, seed=seed):
        client.publish(str(payload["topic"]), json.dumps(payload), qos=0)
        count += 1
    client.disconnect()
    return count


def start_synthetic_attack(scenario: str, options: dict[str, object]) -> dict[str, object]:
    # API mode records intent only; actual MQTT publishing is done by scripts/demo_safe_attack.py.
    if scenario not in SCENARIOS:
        return {"status": "rejected", "reason": "unsupported_scenario", "allowed": sorted(SCENARIOS)}
    return {"status": "started", "scenario": scenario, "simulated": True, "options": options}


def stop_synthetic_attack(scenario: str) -> dict[str, object]:
    if scenario not in SCENARIOS:
        return {"status": "rejected", "reason": "unsupported_scenario", "allowed": sorted(SCENARIOS)}
    return {"status": "stopped", "scenario": scenario, "simulated": True}
