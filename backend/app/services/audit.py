from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, event_type: str, *, device_id: str | None = None, actor: str = "system", details: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(device_id=device_id, event_type=event_type, actor=actor, details=details or {}))
