from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(settings.data_dir) if settings.data_dir else ROOT / "data"
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
            conn.exec_driver_sql('UPDATE episodes SET is_free = 1 WHERE "order" <= 3')
            conn.exec_driver_sql('UPDATE episodes SET is_free = 0 WHERE "order" > 3')
        except Exception:
            pass
        try:
            rows = conn.exec_driver_sql("SELECT id FROM series").all()
            for (sid,) in rows:
                n = conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM episodes WHERE series_id = ?",
                    (sid,),
                ).scalar() or 0
                price = 500 if n <= 6 else 1000 if n <= 14 else 1500
                current = conn.exec_driver_sql(
                    "SELECT unlock_price_tzs FROM series WHERE id = ?",
                    (sid,),
                ).scalar()
                if current in (None, 0, 1000) and price != 1000:
                    conn.exec_driver_sql(
                        "UPDATE series SET unlock_price_tzs = ? WHERE id = ?",
                        (price, sid),
                    )
        except Exception:
            pass
        try:
            flagged = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM series WHERE is_story_of_week = 1"
            ).scalar()
            if not flagged:
                pick = conn.exec_driver_sql(
                    "SELECT id FROM series WHERE published = 1 ORDER BY featured DESC, views DESC LIMIT 1"
                ).first()
                if pick:
                    conn.exec_driver_sql(
                        "UPDATE series SET is_story_of_week = 1 WHERE id = ?",
                        (pick[0],),
                    )
        except Exception:
            pass
