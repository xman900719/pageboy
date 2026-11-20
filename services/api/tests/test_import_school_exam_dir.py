"""学校考试目录批量幂等导入脚本测试（仅使用运行时生成的合成 PDF，绝不含真实试卷）。"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import sys
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import import_school_exam_dir as importer  # noqa: E402
from shutong import models as m  # noqa: E402
from shutong.database import get_db  # noqa: E402
from shutong.main import app  # noqa: E402


def _make_synthetic_pdf_bytes(label: str) -> bytes:
    """使用 PIL 在内存中生成最小单页合成 PDF，仅用于测试导入管线。"""
    img = Image.new("RGB", (400, 120), "white")
    buf = BytesIO()
    img.save(buf, format="PDF", title=label)
    return buf.getvalue()


@pytest.fixture
def synthetic_exam_dir(tmp_path) -> Path:
    d = tmp_path / "十月模拟"
    d.mkdir()
    for name in (
        "数学卷.pdf",
        "数学答.pdf",
        "物理卷.pdf",
        "物理答.pdf",
        "语文卷.pdf",
        "语文答.pdf",
        "道法题.pdf",
        "道法答.pdf",
        "无关说明.txt",
    ):
        if name.endswith(".pdf"):
            (d / name).write_bytes(_make_synthetic_pdf_bytes(name))
        else:
            (d / name).write_text("ignore me", encoding="utf-8")
    return d


def test_build_plan_groups_four_subjects_and_orders_papers_first(synthetic_exam_dir):
    plans = importer.build_plan_from_dir(
        synthetic_exam_dir,
        title_prefix="虚构测试数据：九年级统一练习",
        exam_date="2026-10-15",
        max_points_map={"math": 100, "physics": 70, "chinese": 100, "ethics": 50},
    )
    assert [p.subject for p in plans] == ["math", "physics", "chinese", "ethics"]
    assert plans[0].attachments[0].filename == "数学卷.pdf"
    assert plans[0].attachments[1].filename == "数学答.pdf"
    assert plans[3].attachments[0].filename == "道法题.pdf"
    assert plans[3].attachments[1].filename == "道法答.pdf"
    assert all(p.confirmed_by_user is False for p in plans)
    assert plans[3].max_points == 50.0


def test_direct_import_is_idempotent_and_isolates_attachments(
    synthetic_exam_dir, tmp_path, monkeypatch
):
    priv = tmp_path / "private"
    school_dir = tmp_path / "school-exams"
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(priv))
    monkeypatch.setenv("SHUTONG_SCHOOL_EXAMS_DIR", str(school_dir))
    db_path = tmp_path / "importer_test.sqlite3"
    db_url = f"sqlite+pysqlite:///{db_path}"

    # 使用应用迁移后的空库结构建表
    engine = importer.make_engine(db_url)
    m.Base.metadata.create_all(engine)

    plans = importer.build_plan_from_dir(
        synthetic_exam_dir,
        title_prefix="虚构测试数据：九年级统一练习",
        exam_date="2026-10-15",
    )
    first = importer.import_via_direct(plans, db_url=db_url)
    assert first == {
        "exams_created": 4,
        "exams_existing": 0,
        "attachments_uploaded": 8,
        "attachments_skipped": 0,
    }
    assert not priv.exists() or len(list(priv.iterdir())) == 0

    # 第二次执行必须完全幂等：复用 4 场考试、跳过全部 8 份附件
    second = importer.import_via_direct(plans, db_url=db_url)
    assert second == {
        "exams_created": 0,
        "exams_existing": 4,
        "attachments_uploaded": 0,
        "attachments_skipped": 8,
    }

    # 校验不进题库源表且私有文件保存在 school-exams/<archive_dir>/exam-paper 且权限为 0600
    from shutong import private_files as files

    Session = importer.sessionmaker(bind=engine)
    with Session() as db:
        assert db.scalars(select(m.SourceDocument)).all() == []
        exams = db.scalars(select(m.SchoolExam)).all()
        assert len(exams) == 4
        atts = db.scalars(select(m.SchoolPaperAttachment)).all()
        assert len(atts) == 8
        for att in atts:
            stored_path = files.attachment_file_path(att)
            assert stored_path.is_file()
            assert stored_path.stat().st_mode & 0o777 == 0o600
            assert att.sha256 == sha256(stored_path.read_bytes()).hexdigest()


def test_dry_run_makes_no_changes(synthetic_exam_dir, tmp_path, monkeypatch):
    priv = tmp_path / "private_dry"
    school_dir = tmp_path / "school_dry"
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(priv))
    monkeypatch.setenv("SHUTONG_SCHOOL_EXAMS_DIR", str(school_dir))
    db_path = tmp_path / "dry.sqlite3"
    db_url = f"sqlite+pysqlite:///{db_path}"
    rc = importer.main(
        [
            "--dir",
            str(synthetic_exam_dir),
            "--title-prefix",
            "虚构测试数据：预览",
            "--exam-date",
            "2026-10-15",
            "--direct",
            "--db-url",
            db_url,
            "--dry-run",
        ]
    )
    assert rc == 0
    assert not db_path.exists()
    assert not priv.exists()


def test_api_mode_validates_and_uploads_idempotently(
    client, auth, synthetic_exam_dir, tmp_path, monkeypatch
):
    """通过 TestClient 拦截 HTTP 请求，验证 import_via_api 的请求序列与幂等性。"""
    priv = tmp_path / "private_api"
    school_dir = tmp_path / "school_api"
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(priv))
    monkeypatch.setenv("SHUTONG_SCHOOL_EXAMS_DIR", str(school_dir))

    class _FakeResp:
        def __init__(self, status_code: int, content: bytes):
            self.status = status_code
            self._content = content

        def read(self) -> bytes:
            return self._content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=60):
        method = req.get_method()
        url = req.full_url
        path = url.split("http://unit.test", 1)[1]
        headers = dict(req.header_items())
        body = req.data
        if method == "GET":
            resp = client.get(path, headers=headers)
        else:
            resp = client.post(path, content=body, headers=headers)
        if resp.status_code >= 400:
            from urllib.error import HTTPError

            raise HTTPError(url, resp.status_code, "ERR", {}, BytesIO(resp.content))
        return _FakeResp(resp.status_code, resp.content)

    monkeypatch.setattr(importer, "urlopen", fake_urlopen)
    plans = importer.build_plan_from_dir(
        synthetic_exam_dir,
        title_prefix="虚构测试数据：API 导入",
        exam_date="2026-10-15",
    )
    first = importer.import_via_api(plans, api_url="http://unit.test", token=auth["Authorization"].split(" ", 1)[1])
    assert first == {
        "exams_created": 4,
        "exams_existing": 0,
        "attachments_uploaded": 8,
        "attachments_skipped": 0,
    }
    second = importer.import_via_api(plans, api_url="http://unit.test", token=auth["Authorization"].split(" ", 1)[1])
    assert second == {
        "exams_created": 0,
        "exams_existing": 4,
        "attachments_uploaded": 0,
        "attachments_skipped": 8,
    }

    # 验证通过 API 可查询到道法考试详情及其 2 份附件（且无 storage_key）
    ethics_list = client.get("/api/school-exams?subject=ethics", headers=auth).json()
    assert len(ethics_list) == 1
    detail = client.get(f"/api/school-exams/{ethics_list[0]['id']}", headers=auth).json()
    assert [a["filename"] for a in detail["attachments"]] == ["道法题.pdf", "道法答.pdf"]
    assert all("storage_key" not in a for a in detail["attachments"])
    # 确认总分尚未锁定
    assert detail["confirmed_by_user"] is False
    assert get_db is not None and app is not None
