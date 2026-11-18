"""校考同步架构防复发守卫与库级不变量契约测试。

覆盖：
1. AST/源码守卫：禁止在 parser / pipeline 中复制独立的年级映射表或分组逻辑（强制 SSoT）；
2. DB 物理唯一约束：同场 canonical_exam_key 与同考同哈希附件直接 fail-closed；
3. 跨通道脏库演化与声明式对账：k12100 + inbox(grade=None/别名/西校区) + 跨科错配答题卡页自愈 + 连续幂等；
4. 反例：同学年秋/春两学期同型考试不得误合并。
"""

from __future__ import annotations

import ast
from datetime import date
from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shutong import models as m
from shutong import private_files as files
from shutong import school_exam_matcher as matcher
from shutong import school_exam_pipeline as ep
from shutong import school_report_pipeline as rp
from shutong.database import get_db
from shutong.main import app


def assert_school_exam_invariants(db, owner: str = "owner") -> None:
    reports = db.execute(
        select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner)
    ).scalars().all()
    for i in range(len(reports)):
        for j in range(i + 1, len(reports)):
            a, b = reports[i], reports[j]
            a_links = [
                str(link.get("exam_id") or "")
                for link in (a.linked_exam_ids or [])
                if isinstance(link, dict) and link.get("exam_id")
            ]
            assert not matcher.reports_represent_same_exam(
                a_ext_id=a.external_exam_id,
                a_year=a.academic_year,
                a_grade=a.grade,
                a_type=a.exam_type,
                a_seq=a.exam_sequence,
                a_title=a.title,
                a_date=a.exam_date,
                a_linked_ids=a_links,
                b=b,
            ), f"发现同场重复报告未合并: {a.id} vs {b.id}"

    exams = db.execute(
        select(m.SchoolExam).where(m.SchoolExam.learner_id == owner)
    ).scalars().all()
    expected_pages_by_exam: dict[str, set[int]] = {}
    for rep in reports:
        pages_map = rep.answer_card_pages or {}
        for link in rep.linked_exam_ids or []:
            if isinstance(link, dict) and link.get("exam_id") and link.get("subject"):
                subj = str(link["subject"])
                expected_pages_by_exam[str(link["exam_id"])] = {int(p) for p in (pages_map.get(subj) or [])}

    for ex in exams:
        atts = db.execute(
            select(m.SchoolPaperAttachment).where(m.SchoolPaperAttachment.school_exam_id == ex.id)
        ).scalars().all()
        shas = [att.sha256 for att in atts]
        assert len(shas) == len(set(shas)), f"考试 {ex.id} 存在重复 sha256 附件"
        if ex.id in expected_pages_by_exam:
            allowed = {f"报告答题卡-{ex.subject}-第{p}页.png" for p in expected_pages_by_exam[ex.id]}
            actual_auto = {att.filename for att in atts if att.filename.startswith(f"报告答题卡-{ex.subject}-第")}
            assert actual_auto <= allowed, f"考试 {ex.id} 残留过期/跨科答题卡: {actual_auto - allowed}"


def test_ssot_no_duplicate_grade_mapping_clones():
    shutong_dir = Path(matcher.__file__).resolve().parent
    forbidden_funcs = {"_grade_key", "_norm_grade_short", "_norm_report_type_short"}
    for mod_name in ("school_report_parser.py", "school_report_pipeline.py", "school_exam_pipeline.py"):
        src = (shutong_dir / mod_name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        overlap = defined & forbidden_funcs
        assert not overlap, f"{mod_name} 不得复制独立映射函数 {overlap}，请统一调用 school_exam_matcher"
        assert "normalize_grade" in src, f"{mod_name} 必须从 school_exam_matcher 引入 normalize_grade"


def test_canonical_exam_key_separates_fall_and_spring_terms():
    fall_mid = matcher.build_canonical_exam_key(
        academic_year="2026-2027",
        grade="初三年级",
        exam_type="期中考试",
        title="26-27学年秋学期期中考试",
        exam_date="2026-11-12",
    )
    spring_mid = matcher.build_canonical_exam_key(
        academic_year="2026-2027",
        grade="9",
        exam_type="期中考试",
        title="26-27学年春学期期中考试",
        exam_date="2027-04-20",
    )
    assert fall_mid == "2026-2027|9|midterm|T1"
    assert spring_mid == "2026-2027|9|midterm|T2"
    assert fall_mid != spring_mid


def test_db_unique_constraints_fail_closed(client):
    db = next(app.dependency_overrides[get_db]())
    try:
        ckey = "2026-2027|9|unified_practice|T1|1"
        r1 = m.SchoolExamReport(
            learner_id="owner",
            sha256="a" * 64,
            filename="r1.pdf",
            media_type="application/pdf",
            byte_size=10,
            storage_key=files.write_blob(b"%PDF-1.4\n"),
            source_ref="k12100/E1",
            canonical_exam_key=ckey,
            external_exam_id="E1",
        )
        db.add(r1)
        db.commit()

        r2 = m.SchoolExamReport(
            learner_id="owner",
            sha256="b" * 64,
            filename="r2.pdf",
            media_type="application/pdf",
            byte_size=10,
            storage_key=files.write_blob(b"%PDF-1.4\n2"),
            source_ref="inbox/r2.pdf",
            canonical_exam_key=ckey,
        )
        db.add(r2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        ex = m.SchoolExam(
            learner_id="owner",
            subject="math",
            exam_date=date(2026, 10, 10),
            title="虚构测试数据",
            earned_points=80,
            max_points=100,
            confirmed_by_user=False,
        )
        db.add(ex)
        db.flush()
        db.add(
            m.SchoolPaperAttachment(
                school_exam_id=ex.id,
                owner_id="owner",
                filename="a.png",
                media_type="image/png",
                sha256="c" * 64,
                byte_size=4,
                storage_key=files.write_blob(b"png1"),
            )
        )
        db.commit()
        db.add(
            m.SchoolPaperAttachment(
                school_exam_id=ex.id,
                owner_id="owner",
                filename="b.png",
                media_type="image/png",
                sha256="c" * 64,
                byte_size=4,
                storage_key=files.write_blob(b"png2"),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_dirty_inventory_reconcile_read_parity_and_idempotency(client, auth, monkeypatch):
    headers = auth
    db = next(app.dependency_overrides[get_db]())
    try:
        math_ex = m.SchoolExam(
            learner_id="owner",
            subject="math",
            exam_date=date(2026, 10, 10),
            title="虚构测试数据 · 26-27学年秋学期统一练习一",
            earned_points=70,
            max_points=100,
            confirmed_by_user=True,
            grade="9",
            exam_type="unified_practice",
            academic_year="2026-2027",
            class_highest=86,
            grade_highest=100,
        )
        eng_ex = m.SchoolExam(
            learner_id="owner",
            subject="english",
            exam_date=date(2026, 10, 10),
            title="虚构测试数据 · 26-27学年秋学期统一练习一",
            earned_points=71,
            max_points=100,
            confirmed_by_user=False,
            grade="初三",
            exam_type="unified_practice",
            academic_year="2026-2027",
            class_highest=93,
            grade_highest=98,
        )
        db.add_all([math_ex, eng_ex])
        db.flush()

        pdf_bytes = b"%PDF-1.4\nfake\n"
        math_png = b"fake-math-card-9"
        eng_png = b"fake-english-card-16"
        eng_sha = sha256(eng_png).hexdigest()

        rep_k12 = m.SchoolExamReport(
            learner_id="owner",
            sha256=sha256(pdf_bytes).hexdigest(),
            filename="统一练习一_分析报告册.pdf",
            media_type="application/pdf",
            byte_size=len(pdf_bytes),
            storage_key=files.write_blob(pdf_bytes),
            source_ref="k12100/EXT-UP1",
            external_exam_id="EXT-UP1",
            title="虚构测试数据 · C2027 26-27学年秋学期统一练习一",
            academic_year="2026-2027",
            grade="9",
            exam_type="统一练习一",
            exam_sequence=1,
            exam_date="2026-10-10",
            report_total_score=141,
            report_total_max=200,
            total_class_highest=179,
            total_grade_highest=198,
            pages=25,
            status="matched",
            match_state="EXACT_MATCH",
            subjects=[
                {"subject": "math", "name": "数学", "score": 70, "max_score": 100, "class_highest": 86, "grade_highest": 100},
                {"subject": "english", "name": "英语", "score": 71, "max_score": 100, "class_highest": 93, "grade_highest": 98},
            ],
            answer_card_pages={"math": [9], "english": [16]},
            linked_exam_ids=[
                {"subject": "math", "exam_id": math_ex.id},
                {"subject": "english", "exam_id": eng_ex.id},
            ],
        )
        inbox_bytes = b"%PDF-1.4\ninbox-west\n"
        rep_inbox = m.SchoolExamReport(
            learner_id="owner",
            sha256=sha256(inbox_bytes).hexdigest(),
            filename="统一练习一（西校区）_分析报告册.pdf",
            media_type="application/pdf",
            byte_size=len(inbox_bytes),
            storage_key=files.write_blob(inbox_bytes),
            source_ref="inbox/十月/西校区.pdf",
            external_exam_id=None,
            title="虚构测试数据 · C2027 26-27学年秋学期统一练习一 (西校区)",
            academic_year="2026-2027",
            grade="初三年级",
            exam_type="统一练习一",
            exam_sequence=1,
            exam_date=None,
            pages=25,
            status="needs_review",
            match_state="NEEDS_REVIEW",
            subjects=[{"subject": "math", "name": "数学", "score": 70, "max_score": 100}],
            linked_exam_ids=[{"subject": "math", "exam_id": math_ex.id}],
        )
        db.add_all([rep_k12, rep_inbox])
        db.flush()

        # 制造历史跨科错配残留：math 挂载了 page 9 与本属 english 的 page 16
        db.add_all([
            m.SchoolExamReportAttachment(
                report_id=rep_k12.id, learner_id="owner", subject="math", page_number=9,
                filename="答题卡-math-9.png", media_type="image/png", byte_size=len(math_png),
                storage_key=files.write_blob(math_png), sha256=sha256(math_png).hexdigest(),
            ),
            m.SchoolExamReportAttachment(
                report_id=rep_k12.id, learner_id="owner", subject="math", page_number=16,
                filename="答题卡-math-16.png", media_type="image/png", byte_size=len(eng_png),
                storage_key=files.write_blob(eng_png), sha256=eng_sha,
            ),
            m.SchoolExamReportAttachment(
                report_id=rep_k12.id, learner_id="owner", subject="english", page_number=16,
                filename="答题卡-english-16.png", media_type="image/png", byte_size=len(eng_png),
                storage_key=files.write_blob(eng_png), sha256=eng_sha,
            ),
            m.SchoolPaperAttachment(
                school_exam_id=math_ex.id, owner_id="owner",
                filename="报告答题卡-math-第9页.png", media_type="image/png",
                sha256=sha256(math_png).hexdigest(), byte_size=len(math_png),
                storage_key=files.write_blob(math_png),
            ),
            m.SchoolPaperAttachment(
                school_exam_id=math_ex.id, owner_id="owner",
                filename="报告答题卡-math-第16页.png", media_type="image/png",
                sha256=eng_sha, byte_size=len(eng_png),
                storage_key=files.write_blob(eng_png),
            ),
        ])
        db.commit()

        # 1. 读路径在未跑合并前就必须折叠成唯一场次，绝不把 1 场渲染为 2 场
        center = client.get("/api/school-exams/sync-center", headers=headers).json()
        assert len(center["synced_reports"]) == 1
        assert center["synced_reports"][0]["external_exam_id"] == "EXT-UP1"
        reports_list = client.get("/api/school-exams/reports", headers=headers).json()
        assert len(reports_list) == 1

        # 2. 执行本地补全合并：合并 2->1、清理数学错配的第 16 页英语卡、规范 english 年级且保持独立待核对
        monkeypatch.setattr(rp, "parse_report_pdf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("not needed")))
        summary = rp.hydrate_incomplete_local_reports(db, owner="owner")
        assert summary["deduped_reports"] == 1
        db.expire_all()
        assert_school_exam_invariants(db, "owner")

        db.refresh(math_ex)
        db.refresh(eng_ex)
        assert math_ex.confirmed_by_user is True
        assert eng_ex.confirmed_by_user is False
        assert eng_ex.grade == "9"

        math_cards = db.execute(
            select(m.SchoolPaperAttachment).where(m.SchoolPaperAttachment.school_exam_id == math_ex.id)
        ).scalars().all()
        assert [c.filename for c in math_cards] == ["报告答题卡-math-第9页.png"]

        # 3. 连续二次执行必须严格幂等（零重复变更）
        summary2 = rp.hydrate_incomplete_local_reports(db, owner="owner")
        assert summary2["deduped_reports"] == 0
        assert summary2["cards_synced"] == 0
        assert summary2["ranks_synced"] == 0

        # 4. 模拟 inbox 再次扫入缺失 grade 且带 (西校区) 后缀的同场不同哈希 PDF，绝不新建重复行或覆盖权威标题
        from shutong.school_report_parser import ReportDocument, ReportIdentity, ReportSubject
        fake_doc = ReportDocument(
            kind="exam_analysis_report",
            confidence="high",
            identity=ReportIdentity(
                title="虚构测试数据 · C2027 26-27学年秋学期统一练习一 (西校区)",
                academic_year="2026-2027",
                grade=None,
                exam_type="统一练习一",
                exam_sequence=1,
                exam_month=None,
                report_time="2026年11月15日",
                source_sha256="f" * 64,
            ),
            subjects=[ReportSubject(subject="math", name="数学", score=70, max_score=100)],
            pages=25,
        )
        monkeypatch.setattr(rp, "parse_report_pdf", lambda *a, **k: fake_doc)
        merged_rep, created = rp.register_report_bytes(
            db,
            owner="owner",
            data=b"%PDF-1.4\nrescan-inbox-different-bytes",
            filename="C2027_西校区.pdf",
            source_ref="inbox/十月/西校区.pdf",
        )
        db.commit()
        assert created is False
        assert merged_rep.id == rep_k12.id
        assert "西校区" not in (merged_rep.title or "")
        assert_school_exam_invariants(db, "owner")
    finally:
        db.close()
