from simulator.attacks.safe_attacks import attack_events


def test_safe_attack_scenarios_are_synthetic() -> None:
    events = attack_events("unknown_destination", device_id="camera-01", intensity=3, seed=42)
    assert events
    assert all(event["destination"] == "unknown-simulated-destination" for event in events)
