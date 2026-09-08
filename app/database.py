from pathlib import Path
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

ROOT = Path(__file__).resolve().parents[1]


def _resolve_data_dir() -> Path:
    if settings.data_dir:
        return Path(settings.data_dir)
    railway = Path("/data")
    if railway.is_dir() and os.access(railway, os.W_OK):
        return railway
    return ROOT / "data"


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)

db_url = settings.database_url
if db_url.startswith("postgres://"):
    db_url = "postgresql+psycopg://" + db_url[len("postgres://") :]
elif db_url.startswith("postgresql://") and "+psycopg" not in db_url:
    db_url = "postgresql+psycopg://" + db_url[len("postgresql://") :]
if db_url.startswith("sqlite"):
    db_path = (DATA_DIR / "qisas.db").resolve()
    db_url = "sqlite:///" + db_path.as_posix()

is_sqlite = db_url.startswith("sqlite")
engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False} if is_sqlite else {},
    **(
        {}
        if is_sqlite
        else {
            "pool_pre_ping": True,
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_recycle": 1800,
        }
    ),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema() -> None:
    """Add Phase-1 monetization columns to existing SQLite databases."""
    statements = [
        "ALTER TABLE series ADD COLUMN unlock_price_tzs INTEGER DEFAULT 1000",
        "ALTER TABLE series ADD COLUMN is_story_of_week BOOLEAN DEFAULT 0",
        "ALTER TABLE series ADD COLUMN sponsored_plays INTEGER DEFAULT 0",
        "ALTER TABLE series ADD COLUMN sponsor_pool INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN streak_days INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN last_visit_date VARCHAR",
        "ALTER TABLE users ADD COLUMN badges TEXT DEFAULT '[]'",
    ]
    with engine.begin() as conn:
        for sql in statements:
            try:
                conn.exec_driver_sql(sql)
            except Exception:
                pass
        try:
            conn.exec_driver_sql('UPDATE episodes SET is_free = 1 WHERE "order" <= 1')
            conn.exec_driver_sql('UPDATE episodes SET is_free = 0 WHERE "order" > 1')
        except Exception:
            pass
        for sql in (
            "ALTER TABLE episodes ALTER COLUMN poster_url TYPE TEXT",
            "ALTER TABLE series ALTER COLUMN image TYPE TEXT",
            "ALTER TABLE series ALTER COLUMN backdrop_image TYPE TEXT",
        ):
            try:
                conn.exec_driver_sql(sql)
            except Exception:
                pass
        try:
            from sqlalchemy import text

            rows = conn.execute(text("SELECT id FROM series")).all()
            for (sid,) in rows:
                n = conn.execute(
                    text("SELECT COUNT(*) FROM episodes WHERE series_id = :sid"),
                    {"sid": sid},
                ).scalar() or 0
                price = 500 if n <= 6 else 1000 if n <= 14 else 1500
                current = conn.execute(
                    text("SELECT unlock_price_tzs FROM series WHERE id = :sid"),
                    {"sid": sid},
                ).scalar()
                if current in (None, 0, 1000) and price != 1000:
                    conn.execute(
                        text("UPDATE series SET unlock_price_tzs = :price WHERE id = :sid"),
                        {"price": price, "sid": sid},
                    )
        except Exception:
            pass
