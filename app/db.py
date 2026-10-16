"""SQLite 数据库会话与建表。"""
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

# 确保 data 目录存在
db_path = settings.database_url.replace("sqlite:///", "")
if db_path.startswith("./"):
    db_path = str(Path(__file__).resolve().parent.parent / db_path[2:])
Path(db_path).parent.mkdir(parents=True, exist_ok=True)

# 重新规范化 URL
_url = f"sqlite:///{db_path}" if settings.database_url.startswith("sqlite") else settings.database_url

engine = create_engine(
    _url,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_sqlite() -> None:
    """为已有库补 OHLC 列（create_all 不会 ALTER）。"""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(price_points)")).fetchall()
        if not rows:
            return
        cols = {r[1] for r in rows}
        for col in ("open_price", "high_price", "low_price", "close_price"):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE price_points ADD COLUMN {col} FLOAT"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()
