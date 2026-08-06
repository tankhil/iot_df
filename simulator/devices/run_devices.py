import argparse
import json
import random
import time
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from simulator.devices.profiles import PROFILES, DeviceProfile


def event(profile: DeviceProfile, rng: random.Random) -> dict[str, object]:
    size = max(32, int(rng.gauss(profile.base_message_size, profile.base_message_size * 0.08)))
    return {
        "device_id": profile.device_id,
        "device_type": profile.device_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "topic": f"iot/{profile.device_id}/telemetry",
        "message_size": size,
        "destination": "mqtt-broker",
        "auth_success": True,
        "value": round(rng.uniform(profile.value_min, profile.value_max), 3),
    }


def publish_once(client: mqtt.Client, profile: DeviceProfile, rng: random.Random) -> None:
    payload = event(profile, rng)
    client.publish(payload["topic"], json.dumps(payload), qos=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run safe simulated IoT devices")
    parser.add_argument("--host", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-scale", type=float, default=1.0)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="iot-simulator")
    client.connect(args.host, args.port, keepalive=60)
    next_publish = {profile.device_id: 0.0 for profile in PROFILES}
    while True:
        now = time.monotonic()
        for profile in PROFILES:
            if args.once or now >= next_publish[profile.device_id]:
                publish_once(client, profile, rng)
                next_publish[profile.device_id] = now + profile.interval_seconds * args.interval_scale
        client.loop(timeout=0.1)
        if args.once:
            break
        time.sleep(0.25)


if __name__ == "__main__":
    main()
