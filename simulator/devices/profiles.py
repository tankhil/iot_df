from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    device_id: str
    device_type: str
    interval_seconds: float
    base_message_size: int
    value_min: float
    value_max: float


PROFILES = [
    DeviceProfile("temperature-01", "temperature_sensor", 30.0, 148, 18.0, 29.0),
    DeviceProfile("camera-01", "smart_camera", 5.0, 1400, 0.0, 1.0),
    DeviceProfile("lock-01", "smart_lock", 45.0, 220, 0.0, 1.0),
    DeviceProfile("motion-01", "motion_sensor", 20.0, 180, 0.0, 1.0),
    DeviceProfile("industrial-01", "industrial_sensor", 8.0, 520, 40.0, 80.0),
]
