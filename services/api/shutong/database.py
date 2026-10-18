"""Storage adapter; SQLAlchemy must not be imported by the guidance engine."""
from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Base(DeclarativeBase):
    pass

def make_engine(url: str | None = None):
    resolved = url or os.getenv("DATABASE_URL", "sqlite+pysqlite:///./shutong-dev.sqlite3")
    return create_engine(resolved, connect_args={"check_same_thread": False} if resolved.startswith("sqlite") else {}, pool_pre_ping=True)

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as session:
        yield session
