from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def main() -> int:
    settings = get_settings()
    config_path = Path(__file__).resolve().parents[1] / "backend" / "alembic.ini"
    config = Config(str(config_path))
    script = ScriptDirectory.from_config(config)
    expected_heads = set(script.get_heads())
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            actual_rows = connection.execute(text("select version_num from alembic_version")).scalars().all()
    except SQLAlchemyError as exc:
        print({"status": "failed", "reason": "database revision check failed", "error": exc.__class__.__name__})
        return 1
    actual_heads = set(actual_rows)
    if actual_heads != expected_heads:
        print({"status": "failed", "expected_heads": sorted(expected_heads), "actual_heads": sorted(actual_heads)})
        return 1
    print({"status": "ok", "heads": sorted(actual_heads)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
