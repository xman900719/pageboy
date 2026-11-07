from __future__ import annotations
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from shutong.database import Base, get_db
from shutong.main import app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SHUTONG_ADMIN_TOKEN", "test-admin-secret")
    monkeypatch.setenv("SHUTONG_STUDENT_TOKEN", "test-student-secret")
    monkeypatch.setenv("SHUTONG_TOKEN", "test-admin-secret")
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def auth():
    return {"Authorization": "Bearer test-admin-secret"}

@pytest.fixture
def admin_auth():
    return {"Authorization": "Bearer test-admin-secret"}

@pytest.fixture
def student_auth():
    return {"Authorization": "Bearer test-student-secret"}

@pytest.fixture
def published(client, auth):
    r = client.post("/api/admin/sources", json={"title": "虚构测试题源", "subject": "math", "rights_status": "personal_use_reviewed", "verified": True}, headers=auth)
    assert r.status_code == 201
    src = r.json()["id"]
    ids = []
    for i in range(5):
        q = client.post("/api/admin/questions", json={"source_document_id": src, "stem": f"示例题 {i}：1+1=?", "options": ["A. 1", "B. 2"], "correct_answer": "B", "knowledge_ids": ["math.arithmetic"], "max_points": 2}, headers=auth)
        assert q.status_code == 201
        qid=q.json()["id"]
        assert client.post(f"/api/admin/questions/{qid}/review", headers=auth).status_code == 200
        assert client.post(f"/api/admin/questions/{qid}/publish", headers=auth).status_code == 200
        ids.append(qid)
    return ids
