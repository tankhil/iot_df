import argparse

from simulator.attacks.safe_attacks import SCENARIOS, publish_attack


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish isolated safe attack simulation traffic")
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--host", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="camera-01")
    parser.add_argument("--intensity", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    count = publish_attack(
        args.host,
        args.port,
        args.scenario,
        device_id=args.device_id,
        intensity=args.intensity,
        seed=args.seed,
    )
    print(f"published {count} simulated {args.scenario} events for {args.device_id}")


if __name__ == "__main__":
    main()
