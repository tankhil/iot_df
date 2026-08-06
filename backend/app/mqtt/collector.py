import json
import logging

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas.api import TelemetryIn
from app.services.pipeline import ingest_telemetry, run_detection_cycle

logger = logging.getLogger(__name__)


def on_message(_client: mqtt.Client, _userdata: object, message: mqtt.MQTTMessage) -> None:
    try:
        payload = TelemetryIn.model_validate(json.loads(message.payload.decode("utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        logger.warning("Rejected invalid MQTT payload: %s", exc)
        return
    with SessionLocal() as db:
        ingest_telemetry(db, payload)
        run_detection_cycle(db, device_id=payload.device_id)


def run_collector() -> None:
    settings = get_settings()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="telemetry-collector")
    client.on_message = on_message
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    client.subscribe(settings.mqtt_topic)
    client.loop_forever()
