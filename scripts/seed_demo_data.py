import random
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AuditLog, Device, TelemetryEvent
from app.schemas.api import TelemetryIn
from app.services.pipeline import ingest_telemetry, run_detection_cycle
from sqlalchemy import desc, select

from simulator.attacks.safe_attacks import attack_events
from simulator.devices.profiles import PROFILES
from simulator.devices.run_devices import event

DEMO_SEED_VERSION = "demo-seed-v1"
SEED_STARTED_EVENT = "demo.seed.started"
SEED_COMPLETED_EVENT = "demo.seed.completed"


def _existing_marker(db) -> AuditLog | None:
    return db.scalar(
        select(AuditLog).where(
            AuditLog.event_type == SEED_COMPLETED_EVENT,
            AuditLog.details["seed_version"].as_string() == DEMO_SEED_VERSION,
        )
    )


def _seed_anchor(db) -> datetime:
    marker = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.event_type == SEED_STARTED_EVENT,
            AuditLog.details["seed_version"].as_string() == DEMO_SEED_VERSION,
        )
        .order_by(desc(AuditLog.created_at))
    )
    if marker:
        return datetime.fromisoformat(str(marker.details["anchor_timestamp"]))
    anchor = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=50)
    db.add(
        AuditLog(
            event_type=SEED_STARTED_EVENT,
            actor="demo",
            details={
                "seed_version": DEMO_SEED_VERSION,
                "synthetic": True,
                "anchor_timestamp": anchor.isoformat(),
            },
        )
    )
    db.commit()
    return anchor


def _event_exists(db, payload: dict[str, object]) -> bool:
    return (
        db.scalar(
            select(TelemetryEvent.id).where(
                TelemetryEvent.device_id == payload["device_id"],
                TelemetryEvent.timestamp == TelemetryIn.model_validate(payload).timestamp,
                TelemetryEvent.topic == payload["topic"],
                TelemetryEvent.destination == payload["destination"],
            )
        )
        is not None
    )


def main() -> None:
    settings = get_settings()
    rng = random.Random(settings.random_seed)
    with SessionLocal() as db:
        marker = _existing_marker(db)
        if marker:
            device_count = len(list(db.scalars(select(Device.id))))
            telemetry_count = len(list(db.scalars(select(TelemetryEvent.id))))
            print(
                {
                    "seed_version": DEMO_SEED_VERSION,
                    "synthetic": True,
                    "created": 0,
                    "updated": 0,
                    "skipped": telemetry_count,
                    "devices": device_count,
                    "status": "already_seeded",
                }
            )
            return

        created = 0
        skipped = 0
        start = _seed_anchor(db)
        for minute in range(15):
            for profile in PROFILES:
                payload = event(profile, rng)
                payload["timestamp"] = (start + timedelta(seconds=minute * 2)).isoformat()
                if _event_exists(db, payload):
                    skipped += 1
                    continue
                ingest_telemetry(db, TelemetryIn.model_validate(payload))
                run_detection_cycle(db, device_id=profile.device_id)
                created += 1
        for attack_index, payload in enumerate(attack_events("mqtt_flood", device_id="camera-01", intensity=40, seed=42)):
            payload["timestamp"] = (start + timedelta(seconds=40, milliseconds=attack_index)).isoformat()
            if _event_exists(db, payload):
                skipped += 1
                continue
            ingest_telemetry(db, TelemetryIn.model_validate(payload))
            run_detection_cycle(db, device_id="camera-01")
            created += 1
        db.add(
            AuditLog(
                event_type=SEED_COMPLETED_EVENT,
                actor="demo",
                details={
                    "seed_version": DEMO_SEED_VERSION,
                    "synthetic": True,
                    "created": created,
                    "skipped": skipped,
                    "seed": settings.random_seed,
                    "anchor_timestamp": start.isoformat(),
                },
            )
        )
        db.commit()
        device_count = len(list(db.scalars(select(Device.id))))
    print(
        {
            "seed_version": DEMO_SEED_VERSION,
            "synthetic": True,
            "created": created,
            "updated": 0,
            "skipped": skipped,
            "devices": device_count,
            "status": "seeded",
        }
    )


if __name__ == "__main__":
    main()
