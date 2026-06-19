from contextlib import contextmanager
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "runtime"
DATABASE_FILE = Path(os.environ.get("SYSTEMO_DATABASE_FILE", DATA_DIR / "systemo.db"))
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_database():
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    apply_safe_migrations()


def apply_safe_migrations():
    migrations = {
        "users": {
            "email": "VARCHAR",
            "full_name": "VARCHAR",
            "status": "VARCHAR",
            "last_login_at": "VARCHAR",
        },
        "jobs": {
            "app_key": "VARCHAR",
            "display_name": "VARCHAR",
            "winget_id": "VARCHAR",
            "detection_id": "VARCHAR",
        },
    }

    with engine.begin() as connection:
        for table_name, columns in migrations.items():
            existing_columns = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            if not existing_columns:
                continue
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
