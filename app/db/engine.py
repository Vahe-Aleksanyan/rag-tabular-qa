from __future__ import annotations

import os
from dataclasses import dataclass
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class DBConfig:
    host: str
    port: int
    database: str
    user: str
    password: str


def get_db_config() -> DBConfig:
    return DBConfig(
        host=os.getenv("MYSQL_HOST", "db"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE", "ragdb"),
        user=os.getenv("MYSQL_USER", "raguser"),
        password=os.getenv("MYSQL_PASSWORD", "ragpass"),
    )



def get_engine() -> Engine:
    cfg = get_db_config()
    url = f"mysql+pymysql://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.database}"
    return create_engine(url, pool_pre_ping=True)


def ping(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
