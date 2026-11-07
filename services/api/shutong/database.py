"""Storage adapter; SQLAlchemy must not be imported by the guidance engine."""
from __future__ import annotations
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 开发默认库固定为 services/api/shutong-dev.sqlite3，与启动目录无关
DEFAULT_DATABASE_URL = f"sqlite+pysqlite:///{Path(__file__).resolve().parents[1] / 'shutong-dev.sqlite3'}"

class Base(DeclarativeBase):
    pass

def make_engine(url: str | None = None):
    resolved = url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    return create_engine(resolved, connect_args={"check_same_thread": False} if resolved.startswith("sqlite") else {}, pool_pre_ping=True)

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as session:
        yield session
