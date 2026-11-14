from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from shutong.database import Base, get_db
from shutong.home import curriculum_standards_dir
from shutong.main import app


@pytest.fixture(autouse=True, scope="session")
def setup_test_curriculum_standards():
    """在测试环境中确保课程标准文件准备就绪；若宿主 Home 无原件，则在临时目录生成合成原件，不污染源码树。"""
    os.environ["SHUTONG_ALLOW_SYNTHETIC_STANDARDS"] = "1"
    root = Path(__file__).resolve().parents[3]
    sources_path = root / "contracts" / "curriculum_sources.json"

    local_name_map = {
        "chinese": "义务教育语文课程标准（2022年版）.pdf",
        "math": "义务教育数学课程标准（2022年版）（以此为准2022年5月9日）.pdf",
        "english": "义务教育英语课程标准（2022年版）.pdf",
        "physics": "义务教育物理课程标准（2022年版）.pdf",
    }

    host_pdf_dir = curriculum_standards_dir()
    has_all_host_files = host_pdf_dir.is_dir() and all(
        (host_pdf_dir / fname).is_file() for fname in local_name_map.values()
    )
    if not has_all_host_files and sources_path.is_file():
        pdf_dir = Path(tempfile.gettempdir()) / "pageboy-test-standards"
        os.environ["SHUTONG_STANDARDS_DIR"] = str(pdf_dir)
        try:
            with open(sources_path, "r", encoding="utf-8") as f:
                sources = json.load(f)
            pdf_dir.mkdir(parents=True, exist_ok=True)
            for s in sources:
                subj = s.get("subject")
                fname = local_name_map.get(subj)
                if not fname:
                    continue
                fpath = pdf_dir / fname
                # 如果文件不存在，或者已存在但为轻量合成文件，写入最新的合成标记
                if not fpath.exists() or (fpath.is_file() and fpath.stat().st_size < 1024):
                    fpath.write_text(
                        f"%PAGEBOY_SYNTHETIC_STANDARD:{s.get('file_sha256')}:{s.get('byte_size')}\n",
                        encoding="utf-8"
                    )
        except Exception:
            pass
    yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SHUTONG_ADMIN_TOKEN", "test-admin-secret")
    monkeypatch.setenv("SHUTONG_STUDENT_TOKEN", "test-student-secret")
    monkeypatch.setenv("SHUTONG_TOKEN", "test-admin-secret")
    monkeypatch.setenv("SHUTONG_ALLOW_SYNTHETIC_STANDARDS", "1")
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
