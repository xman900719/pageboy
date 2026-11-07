# -*- coding: utf-8 -*-
"""测试真题库与知识点库播种、幂等性、强断言质检与演示数据清理。"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session
from shutong.database import Base
from shutong import models as m

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_validate_corpus_integrity_script():
    """验证 100% 强断言质检工具在当前代码树执行必绿。"""
    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "validate_corpus_integrity.py")], capture_output=True, text=True)
    assert res.returncode == 0, f"质检脚本失败：\n{res.stderr}\n{res.stdout}"
    assert "全量质检成功" in res.stdout


def test_seed_real_corpus_and_idempotency(tmp_path):
    """验证 seed_real_corpus 工具能安全向数据库写入知识点与 2018-2025 真题，且具备幂等性。"""
    from scripts.seed_real_corpus import seed_corpus
    db_file = tmp_path / "test-seed.sqlite3"
    url = f"sqlite+pysqlite:///{db_file}"
    
    # 初始化表结构
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    
    first_run = seed_corpus(db_url=url)
    assert first_run["nodes_created"] == 81
    assert first_run["sources_created"] == 32
    assert first_run["questions_published"] == 350
    assert first_run["links_created"] >= 350
    
    second_run = seed_corpus(db_url=url)
    assert second_run["nodes_created"] == 0
    assert second_run["questions_published"] == 0
    assert second_run["questions_existing"] == 350


def test_seed_real_corpus_attaches_pdfs_and_passes_import_integrity(tmp_path, monkeypatch):
    """验证开启 attach_pdfs=True 时为全部 32 套试卷挂载原件附件（28 份 PDF + 4 份 DOCX）并建立 ImportedQuestion 溯源。"""
    from scripts.seed_real_corpus import seed_corpus
    from shutong.corpus.exam_2025 import ALL_EXAM_PAPERS
    from shutong.ingestion import require_import_integrity
    from test_ingestion import synthetic_docx, synthetic_pdf

    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "priv"))
    corpus_dir = tmp_path / "corpus"
    for paper in ALL_EXAM_PAPERS:
        rel = paper["pdf_relpath"]
        target = corpus_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".docx"):
            target.write_bytes(synthetic_docx(text=f"SYNTHETIC TEST DATA {paper['exam_year']} {paper['subject']}"))
        else:
            target.write_bytes(synthetic_pdf(pages=1, text=f"SYNTHETIC TEST DATA {paper['exam_year']} {paper['subject']}"))

    db_file = tmp_path / "test-seed-pdf.sqlite3"
    url = f"sqlite+pysqlite:///{db_file}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    stats = seed_corpus(db_url=url, corpus_dir=corpus_dir, attach_pdfs=True)
    assert stats["sources_created"] == 32
    assert stats["attachments_linked"] == 32
    assert stats["questions_published"] == 350

    # 幂等复跑不重复创建附件
    second = seed_corpus(db_url=url, corpus_dir=corpus_dir, attach_pdfs=True)
    assert second["attachments_linked"] == 0

    with Session(engine) as session:
        qvs = session.scalars(select(m.QuestionVersion)).all()
        assert len(qvs) == 350
        for qv in qvs:
            require_import_integrity(session, qv)
    engine.dispose()


def test_clean_demo_data_removes_only_demo(tmp_path):
    """验证 clean_demo_data 仅清理演示题源及关联，绝不伤害真实中考题。"""
    from scripts.seed_real_corpus import seed_corpus
    from scripts.clean_demo_data import clean_demo_data
    db_file = tmp_path / "test-clean.sqlite3"
    url = f"sqlite+pysqlite:///{db_file}"

    # 初始化表结构并播种真实真题
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    seed_corpus(db_url=url)

    # 插入一条合成演示题源和题目
    with Session(engine) as session:
        demo_src = m.SourceDocument(
            title="数学虚构演示题源（单元测试）",
            subject="math",
            rights_status="personal_use_reviewed",
            verified=True,
        )
        session.add(demo_src)
        session.flush()

        demo_q = m.Question(source_document_id=demo_src.id, subject="math")
        session.add(demo_q)
        session.flush()

        demo_qv = m.QuestionVersion(
            question_id=demo_q.id,
            version=1,
            stem="虚构单选：1+1=?",
            kind="single_choice",
            options=["A. 1", "B. 2", "C. 3", "D. 4"],
            correct_answer="B",
            max_points=1.0,
            status="published",
        )
        session.add(demo_qv)
        session.commit()

    # 执行清理
    counts = clean_demo_data(dry_run=False, db_url=url)
    assert counts["sources"] == 1
    assert counts["questions"] == 1
    assert counts["question_versions"] == 1

    # 验证真实真题毫发无损（仍为 32 个真实题源、350 道真实试题）
    with Session(engine) as session:
        real_sources = session.scalars(select(m.SourceDocument).where(m.SourceDocument.source_class == "official_exam")).all()
        assert len(real_sources) == 32

        real_questions = session.scalars(select(m.Question).join(m.SourceDocument).where(m.SourceDocument.source_class == "official_exam")).all()
        assert len(real_questions) == 350

    engine.dispose()
