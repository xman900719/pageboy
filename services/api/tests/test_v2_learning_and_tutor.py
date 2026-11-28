"""书童 V2 后端测试：迁移 0009、纯函数成长/组卷、AI 引导防泄密、知识图谱与全量审核发布。"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import inspect

from shutong import ai_tutor
from shutong.database import make_engine
from shutong.guidance import (
    Evidence,
    compose_practice_plan,
    compute_knowledge_mastery,
    summarize_growth,
)
from shutong.taxonomy_audit import audit_and_publish_subject
from shutong.taxonomy_bridge import get_elective_codes


def _publish_mapped_questions(client, admin_auth, items: list[dict]) -> list[str]:
    """辅助创建来源、审核并通过正常流程发布绑定特定考点的练习题。"""
    src_res = client.post(
        "/api/admin/sources",
        json={"title": "虚构测试数据：V2 综合练习题源", "subject": "math", "rights_status": "personal_use_reviewed"},
        headers=admin_auth,
    )
    assert src_res.status_code == 201
    source_id = src_res.json()["id"]
    rev = client.post(
        f"/api/admin/sources/{source_id}/review",
        json={
            "exam_year": 2026,
            "source_url": "https://example.org/v2-math",
            "acquired_at": "2026-11-12",
            "rights_status": "personal_use_reviewed",
            "rights_basis": "虚构测试数据：测试发布闭环",
            "applicable": True,
            "applicability_note": "适用测试",
            "reviewed_by_human": True,
        },
        headers=admin_auth,
    )
    assert rev.status_code == 201

    version_ids: list[str] = []
    for item in items:
        q_res = client.post(
            "/api/admin/questions",
            json={
                "source_document_id": source_id,
                "stem": item["stem"],
                "kind": item.get("kind", "single_choice"),
                "options": item.get("options", ["A. 选项甲", "B. 选项乙"]),
                "correct_answer": item.get("correct_answer", "A"),
                "knowledge_ids": item["knowledge_ids"],
                "max_points": item.get("max_points", 2.0),
            },
            headers=admin_auth,
        )
        assert q_res.status_code == 201
        vid = q_res.json()["id"]
        assert client.post(f"/api/admin/questions/{vid}/review", headers=admin_auth).status_code == 200
        assert client.post(f"/api/admin/questions/{vid}/publish", headers=admin_auth).status_code == 200
        version_ids.append(vid)
    return version_ids


def test_alembic_0009_roundtrip(tmp_path):
    """正例：Alembic 0009 在空库上 upgrade head -> downgrade 0008 -> upgrade head 完整可逆。"""
    db_file = tmp_path / "alembic_0009.sqlite3"
    api_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"}

    up1 = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api_root, env=env, capture_output=True, text=True)
    assert up1.returncode == 0, up1.stderr

    engine = make_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"practice_sessions", "practice_session_items", "ai_tutor_sessions", "ai_tutor_turns"} <= tables
    kn_cols = {col["name"] for col in insp.get_columns("knowledge_nodes")}
    assert "is_elective" in kn_cols
    engine.dispose()

    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0008"], cwd=api_root, env=env, capture_output=True, text=True)
    assert down.returncode == 0, down.stderr

    engine2 = make_engine(f"sqlite:///{db_file}")
    insp2 = inspect(engine2)
    tables2 = set(insp2.get_table_names())
    assert "practice_sessions" not in tables2
    assert "ai_tutor_turns" not in tables2
    kn_cols2 = {col["name"] for col in insp2.get_columns("knowledge_nodes")}
    assert "is_elective" not in kn_cols2
    engine2.dispose()

    up2 = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api_root, env=env, capture_output=True, text=True)
    assert up2.returncode == 0, up2.stderr


def test_guidance_v2_mastery_growth_and_compose():
    """纯函数：过滤选学节点、识别优势/不足/盲区并按薄弱与前置依赖编制有限轮次题组。"""
    nodes = [
        {"code": "dom_num", "name": "数与代数", "domain": "num", "parent_code": None, "level": 1, "is_elective": False},
        {"code": "k_weak", "name": "薄弱考点", "domain": "num", "parent_code": "dom_num", "level": 2, "is_elective": False},
        {"code": "k_prereq", "name": "前置基础", "domain": "num", "parent_code": "dom_num", "level": 2, "is_elective": False},
        {"code": "k_strong", "name": "优势考点", "domain": "num", "parent_code": "dom_num", "level": 2, "is_elective": False},
        {"code": "k_untested", "name": "盲区考点", "domain": "num", "parent_code": "dom_num", "level": 2, "is_elective": False},
        {"code": "k_elective", "name": "选学内容*", "domain": "num", "parent_code": "dom_num", "level": 2, "is_elective": True},
    ]
    evidence = [
        Evidence("e1", "qv1", "k_weak", 0.0, 2.0, True, True),
        Evidence("e2", "qv2", "k_weak", 0.0, 2.0, True, True),
        Evidence("e3", "qv3", "k_weak", 0.0, 2.0, True, True),
        Evidence("e4", "qv4", "k_strong", 2.0, 2.0, True, True),
        Evidence("e5", "qv5", "k_strong", 2.0, 2.0, True, True),
        Evidence("e6", "qv6", "k_strong", 2.0, 2.0, True, True),
    ]
    mastery = compute_knowledge_mastery(nodes, evidence)
    assert all(m["code"] != "k_elective" for m in mastery)
    by_code = {m["code"]: m for m in mastery}
    assert by_code["k_weak"]["mastery_status"] == "weak"
    assert by_code["k_strong"]["mastery_status"] == "mastered"
    assert by_code["k_prereq"]["mastery_status"] == "untested"

    growth = summarize_growth(mastery)
    assert growth["summary_counts"]["weak_count"] == 1
    assert growth["summary_counts"]["mastered_count"] == 1
    assert growth["strengths"][0]["code"] == "k_strong"
    assert growth["weaknesses"][0]["code"] == "k_weak"

    edges = [{"source": "k_prereq", "target": "k_weak", "relation": "前置", "edge_type": "prerequisite"}]
    candidates = [
        {"question_id": "q_s1", "question_version_id": "v_s1", "knowledge_codes": ["k_strong"], "seen_count": 0},
        {"question_id": "q_p1", "question_version_id": "v_p1", "knowledge_codes": ["k_prereq"], "seen_count": 0},
        {"question_id": "q_w1", "question_version_id": "v_w1", "knowledge_codes": ["k_weak"], "seen_count": 1},
        {"question_id": "q_u1", "question_version_id": "v_u1", "knowledge_codes": ["k_untested"], "seen_count": 0},
    ]
    plan = compose_practice_plan(candidates, mastery, edges, target_count=3, purpose="training")
    assert len(plan["items"]) == 3
    qids = [it["question_id"] for it in plan["items"]]
    assert "q_w1" in qids
    assert "q_p1" in qids

    eval_plan = compose_practice_plan(candidates, mastery, edges, target_count=4, purpose="evaluation")
    eval_qids = [it["question_id"] for it in eval_plan["items"]]
    assert "q_w1" not in eval_qids  # evaluation 禁止已见题


def test_practice_session_growth_graph_and_token_isolation(client, admin_auth, student_auth):
    """端到端 API：双令牌隔离、图谱屏蔽选学、智能组卷作答、结算错题且不直接泄密答案。"""
    # 1. 双令牌互访边界
    assert client.post("/api/practice/sessions", json={"subject": "math"}, headers=admin_auth).status_code == 403
    assert client.get("/api/growth/status?subject=math", headers=admin_auth).status_code == 403
    assert client.get("/api/knowledge/graph?subject=math", headers=admin_auth).status_code == 403
    assert client.post("/api/admin/knowledge/nodes/batch-review", json={"items": []}, headers=student_auth).status_code == 403

    # 2. 发布映射到 math.num.real 与 math.func.linear 的测试题（含 3 道用于触发薄弱结论 + 1 道对照）
    _publish_mapped_questions(
        client,
        admin_auth,
        [
            {"stem": "虚构测试数据：有理数与实数题 1", "knowledge_ids": ["math.num.real"], "correct_answer": "A"},
            {"stem": "虚构测试数据：有理数与实数题 2", "knowledge_ids": ["math.num.real"], "correct_answer": "A"},
            {"stem": "虚构测试数据：有理数与实数题 3", "knowledge_ids": ["math.num.real"], "correct_answer": "A"},
            {"stem": "虚构测试数据：一次函数巩固题 1", "knowledge_ids": ["math.func.linear"], "correct_answer": "A"},
        ],
    )

    # 3. 图谱确认选学节点绝对不出现在学生端
    electives = get_elective_codes("math")
    graph_res = client.get("/api/knowledge/graph?subject=math", headers=student_auth)
    assert graph_res.status_code == 200
    graph_codes = {n["code"] for n in graph_res.json()["nodes"]}
    assert electives.isdisjoint(graph_codes), f"学生图谱不得暴露选学节点：{electives & graph_codes}"
    assert len(graph_res.json()["edges"]) > 0

    # 4. 开始智能综合练习（4题）：前 3 题故意答错，第 4 题答对
    sess_res = client.post(
        "/api/practice/sessions",
        json={"subject": "math", "target_count": 4, "purpose": "training"},
        headers=student_auth,
    )
    assert sess_res.status_code == 201
    sess = sess_res.json()
    session_id = sess["id"]
    assert sess["total_items"] == 4
    assert sess["current_item"] is not None
    assert "correct_answer" not in sess["current_item"]

    for idx in range(4):
        cur = sess["current_item"]
        chosen = "A" if idx == 3 else "B"
        att = client.post(
            "/api/practice/attempts",
            json={
                "client_attempt_id": str(uuid.uuid4()),
                "exposure_id": cur["exposure_id"],
                "answer": chosen,
                "hints_used": False,
            },
            headers=student_auth,
        )
        assert att.status_code == 201
        if idx < 3:
            nxt = client.post(f"/api/practice/sessions/{session_id}/next", headers=student_auth)
            assert nxt.status_code == 200
            sess = nxt.json()

    # 5. 交卷结算：错题列表不能提前泄露 correct_answer
    comp = client.post(f"/api/practice/sessions/{session_id}/complete", headers=student_auth)
    assert comp.status_code == 200
    comp_data = comp.json()
    assert comp_data["answered_count"] == 4
    assert comp_data["wrong_count"] >= 2
    assert "correct_answer" not in comp_data["wrong_items"][0]

    # 6. 成长状态应准确识别薄弱节点
    growth_res = client.get("/api/growth/status?subject=math", headers=student_auth)
    assert growth_res.status_code == 200
    assert growth_res.json()["summary_counts"]["weak_count"] >= 1


def test_ai_tutor_socratic_guardrail_and_error_handling(client, admin_auth, student_auth, monkeypatch):
    """AI 错题引导：未配置返回 503；直接泄题响应被服务端拦截替换；多轮合法引导保留且超时不留脏记录。"""
    _publish_mapped_questions(
        client,
        admin_auth,
        [{"stem": "虚构测试数据：求解方程 $x + 3 = 7$", "options": ["A. 4", "B. 10"], "correct_answer": "A", "knowledge_ids": ["math.num.real"]}],
    )
    sess = client.post("/api/practice/sessions", json={"subject": "math", "target_count": 1}, headers=student_auth).json()
    exp_id = sess["current_item"]["exposure_id"]
    att = client.post(
        "/api/practice/attempts",
        json={"client_attempt_id": str(uuid.uuid4()), "exposure_id": exp_id, "answer": "B", "hints_used": False},
        headers=student_auth,
    ).json()
    attempt_id = att["id"]

    # 1. 未配置 API KEY -> 503
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    res_no_key = client.post(f"/api/tutor/attempts/{attempt_id}/start", headers=student_auth)
    assert res_no_key.status_code == 503

    # 2. Mock httpx 返回“直接泄露答案”文本 -> 防泄密守卫必须拦截改写
    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("SHUTONG_AI_BASE_URL", "https://api.deepseek.com")

    class FakeResp:
        def __init__(self, content: str):
            self._content = content
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "deepseek-chat",
                "choices": [{"message": {"content": self._content}}],
            }

    replies = iter([
        "这题选 A，因为正确答案为 A。",
        "很好！你已经注意到需要移项，那把 +3 移到右边应该变为什么运算符号？",
    ])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResp(next(replies))

    monkeypatch.setattr(ai_tutor.httpx, "Client", FakeClient)

    started = client.post(f"/api/tutor/attempts/{attempt_id}/start", headers=student_auth)
    assert started.status_code == 201
    sdata = started.json()
    assert sdata["started"] is True
    assert len(sdata["turns"]) == 1
    assert sdata["turns"][0]["sanitized_guard_triggered"] is True
    assert "选 A" not in sdata["turns"][0]["content"]

    # 幂等再次 start 不应再请求上游
    started_again = client.post(f"/api/tutor/attempts/{attempt_id}/start", headers=student_auth)
    assert started_again.status_code == 201
    assert started_again.json()["id"] == sdata["id"]

    # 多轮引导回复：合法苏格拉底文本不触发拦截
    msg_res = client.post(
        f"/api/tutor/sessions/{sdata['id']}/message",
        json={"content": "我觉得要把等号左边的 +3 移到右边去"},
        headers=student_auth,
    )
    assert msg_res.status_code == 200
    mdata = msg_res.json()
    assert len(mdata["turns"]) == 3
    assert mdata["turns"][2]["sanitized_guard_triggered"] is False
    assert "移到右边" in mdata["turns"][2]["content"]

    # 3. 上游超时 -> 503 且轮次数保持 3（无孤儿 user 发言）
    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(ai_tutor.httpx, "Client", TimeoutClient)
    fail_msg = client.post(
        f"/api/tutor/sessions/{sdata['id']}/message",
        json={"content": "是变成减 3 吗？"},
        headers=student_auth,
    )
    assert fail_msg.status_code == 503
    after_fail = client.get(f"/api/tutor/attempts/{attempt_id}", headers=student_auth)
    assert len(after_fail.json()["turns"]) == 3


def test_batch_review_and_full_taxonomy_audit_publish(client, admin_auth):
    """管理端批量审核接口检验与四学科 135 节点全量条款审核发布验证。"""
    # 先验证缺少真实审核意见被拒绝
    bad_batch = client.post(
        "/api/admin/knowledge/nodes/batch-review",
        json={"items": [{"node_id": "non-existent", "reviewer_id": "", "review_status": "approved", "review_opinion": " "}]},
        headers=admin_auth,
    )
    assert bad_batch.status_code == 422

    # 借由应用同库验证批量接口与全量审计发布模块
    from shutong.database import get_db
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        total_published = 0
        for subj in ("math", "chinese", "english", "physics"):
            res = audit_and_publish_subject(db, subject=subj, reviewer_id="test_reviewer")
            assert res["release_status"] == "published"
            assert res["approved_now"] > 0
            total_published += res["total_candidate_nodes"]
        assert total_published == 135

        # 幂等二跑：全部保持 already_published
        res_idempotent = audit_and_publish_subject(db, subject="math", reviewer_id="test_reviewer")
        assert res_idempotent["release_status"] == "already_published"
        assert res_idempotent["approved_now"] == 0

        # 验证北京市中考全科专家 135 个节点专项定位全覆盖与 force_update_existing 快照刷新
        from shutong.taxonomy_audit import BEIJING_ZHONGKAO_EXPERT_NOTES, _load_candidates
        from shutong import models as m
        from sqlalchemy import select

        all_contract_codes = {
            c["code"]
            for subj in ("math", "chinese", "english", "physics")
            for c in _load_candidates(subj)
        }
        assert len(all_contract_codes) == 135
        assert set(BEIJING_ZHONGKAO_EXPERT_NOTES.keys()) == all_contract_codes

        res_force = audit_and_publish_subject(
            db,
            subject="math",
            reviewer_id="beijing_zhongkao_expert",
            force_update_existing=True,
        )
        assert res_force["release_status"] == "published"
        assert res_force["approved_now"] == 48
        rel = db.scalar(
            select(m.KnowledgeTaxonomyRelease).where(
                m.KnowledgeTaxonomyRelease.subject == "math",
                m.KnowledgeTaxonomyRelease.release_version == "math-v2022.1.0",
            )
        )
        assert rel is not None
        assert rel.status == "published"
        assert rel.snapshot["curriculum_sources"]
        assert rel.published_by == "beijing_zhongkao_expert"
        assert isinstance(rel.snapshot, dict)
        assert rel.snapshot["total_nodes"] == 48
        assert all(
            item["reviewer_id"] == "beijing_zhongkao_expert"
            and "【北京市中考全科教研专家终审通过】" in item["review_opinion"]
            for item in rel.snapshot["nodes"]
        )

        # 验证管理端发布快照查询接口返回 200 且计数正确
        rel_api = client.get("/api/admin/knowledge/releases?subject=math", headers=admin_auth)
        assert rel_api.status_code == 200
        rel_list = rel_api.json()
        assert len(rel_list) == 1
        assert rel_list[0]["release_version"] == "math-v2022.1.0"
        assert rel_list[0]["total_nodes"] == 48
        assert rel_list[0]["status"] == "published"
    finally:
        db.close()


def test_alembic_0020_roundtrip(tmp_path):
    """正例：Alembic 0020 在空库上 upgrade head -> downgrade 0019 -> upgrade head 完整可逆。"""
    db_file = tmp_path / "alembic_0020.sqlite3"
    api_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"}

    up1 = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api_root, env=env, capture_output=True, text=True)
    assert up1.returncode == 0, up1.stderr

    engine = make_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    assert "ai_error_diagnoses" in set(insp.get_table_names())
    turn_cols = {col["name"] for col in insp.get_columns("ai_tutor_turns")}
    assert "sanitized_guard_triggered" in turn_cols
    engine.dispose()

    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0019"], cwd=api_root, env=env, capture_output=True, text=True)
    assert down.returncode == 0, down.stderr

    engine2 = make_engine(f"sqlite:///{db_file}")
    insp2 = inspect(engine2)
    assert "ai_error_diagnoses" not in set(insp2.get_table_names())
    turn_cols2 = {col["name"] for col in insp2.get_columns("ai_tutor_turns")}
    assert "sanitized_guard_triggered" not in turn_cols2
    engine2.dispose()

    up2 = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api_root, env=env, capture_output=True, text=True)
    assert up2.returncode == 0, up2.stderr


def test_admin_wrong_diagnostics_and_level2_solution_loop(client, admin_auth, student_auth, monkeypatch):
    """端到端：引导对话持久化 -> 管理端回放与 AI 错因三选一 -> 选定对策透出至学生端（Level 2）。"""
    import json as json_lib

    _publish_mapped_questions(
        client,
        admin_auth,
        [
            {"stem": "虚构测试数据：已知 2x - 4 = 0，求 x", "knowledge_ids": ["math.num.real"], "correct_answer": "A"},
            {"stem": "虚构测试数据：已知 x + 3 = 5，求 x", "knowledge_ids": ["math.func.linear"], "correct_answer": "A"},
        ],
    )

    # 1. 双令牌隔离：学生 Token 访问管理端诊断接口一律 403
    assert client.get("/api/admin/wrong-diagnostics?subject=math", headers=student_auth).status_code == 403

    # 2. 学生做 2 题：第 1 题答对（满分），第 2 题答错（选 B）
    sess = client.post("/api/practice/sessions", json={"subject": "math", "target_count": 2}, headers=student_auth).json()
    q1 = sess["current_item"]
    att1 = client.post(
        "/api/practice/attempts",
        json={"client_attempt_id": str(uuid.uuid4()), "exposure_id": q1["exposure_id"], "answer": "A", "hints_used": False},
        headers=student_auth,
    ).json()
    sess2 = client.post(f"/api/practice/sessions/{sess['id']}/next", headers=student_auth).json()
    q2 = sess2["current_item"]
    att2 = client.post(
        "/api/practice/attempts",
        json={"client_attempt_id": str(uuid.uuid4()), "exposure_id": q2["exposure_id"], "answer": "B", "hints_used": False},
        headers=student_auth,
    ).json()
    wrong_id = att2["id"]
    right_id = att1["id"]

    # 反例：满分作答不可用于错因诊断
    assert client.get(f"/api/admin/wrong-diagnostics/{right_id}", headers=admin_auth).status_code == 422

    # 3. 无引导对话前，管理端列表可见错题且允许手动触发分析
    monkeypatch.setenv("SHUTONG_AI_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("SHUTONG_AI_BASE_URL", "https://api.deepseek.com")

    class FakeResp:
        def __init__(self, content: str):
            self._content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"model": "deepseek-chat", "choices": [{"message": {"content": self._content}}]}

    # 3a. 反例：上游返回非 3 个方案 JSON -> 503 Fail-Closed
    class BadAnalysisClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResp(json_lib.dumps({"root_cause_summary": "x", "evidence_from_dialogue": "y", "solutions": []}))

    monkeypatch.setattr(ai_tutor.httpx, "Client", BadAnalysisClient)
    fail_analyze = client.post(f"/api/admin/wrong-diagnostics/{wrong_id}/analyze", headers=admin_auth)
    assert fail_analyze.status_code == 503

    # 4. 学生开启引导并多轮对话，验证对话及 sanitized_guard_triggered 落库
    tutor_replies = iter(["先把题目里的常数项看清楚，移项时符号怎么变化？", "对的，移到等号右侧后要变号。"])

    class GoodTutorClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResp(next(tutor_replies))

    monkeypatch.setattr(ai_tutor.httpx, "Client", GoodTutorClient)
    ts = client.post(f"/api/tutor/attempts/{wrong_id}/start", headers=student_auth).json()
    client.post(f"/api/tutor/sessions/{ts['id']}/message", json={"content": "移项后我忘记变号了"}, headers=student_auth)

    # 管理端列表与详情应能完整回放已保存的多轮引导对话
    list_res = client.get("/api/admin/wrong-diagnostics?subject=math", headers=admin_auth)
    assert list_res.status_code == 200
    rows = list_res.json()
    assert len(rows) == 1
    assert rows[0]["attempt_id"] == wrong_id
    assert rows[0]["tutor_turn_count"] == 3
    assert rows[0]["has_diagnosis"] is False

    detail_before = client.get(f"/api/admin/wrong-diagnostics/{wrong_id}", headers=admin_auth)
    assert detail_before.status_code == 200
    assert detail_before.json()["correct_answer"] == "A"
    assert len(detail_before.json()["tutor_turns"]) == 3
    assert detail_before.json()["tutor_turns"][1]["content"] == "移项后我忘记变号了"

    # 反例：未生成诊断前不能直接选方案
    assert (
        client.post(
            f"/api/admin/wrong-diagnostics/{wrong_id}/select-solution",
            json={"option_id": "opt_1"},
            headers=admin_auth,
        ).status_code
        == 404
    )

    # 5. 管理端手动触发 AI 错因分析，返回真正原因 + 3 个可选方案并落库
    valid_analysis = {
        "cognitive_gap_type": "concept_confusion",
        "root_cause_summary": "学生对等式基本性质（移项变号本质）理解不牢，机械记忆移项步骤导致符号出错。",
        "evidence_from_dialogue": "学生在引导第2轮主动承认“移项后忘记变号”，反映对等式两边同时加减的本质缺乏条件反射。",
        "solutions": [
            {
                "option_id": "opt_1",
                "title": "等式天平原理手写推导",
                "approach_focus": "概念纠偏",
                "rationale": "从两边同减同加消除机械移项错误。",
                "action_steps": ["先写完整两边同减步骤", "再对照省略形式口述变号依据"],
            },
            {
                "option_id": "opt_2",
                "title": "移项符号双色圈画法",
                "approach_focus": "习惯与审题",
                "rationale": "通过视觉锚点防止跨等号丢符号。",
                "action_steps": ["跨过等号前先用红笔圈出正负号", "重写一遍新符号再合并同类项"],
            },
            {
                "option_id": "opt_3",
                "title": "3 题同构含负号变式微练",
                "approach_focus": "变式迁移",
                "rationale": "用不同符号组合巩固迁移稳定性。",
                "action_steps": ["连续完成3道含负号移项小题", "每题做完代入原式口算验根"],
            },
        ],
    }

    class GoodAnalysisClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResp(f"```json\n{json_lib.dumps(valid_analysis, ensure_ascii=False)}\n```")

    monkeypatch.setattr(ai_tutor.httpx, "Client", GoodAnalysisClient)
    analyzed = client.post(f"/api/admin/wrong-diagnostics/{wrong_id}/analyze", headers=admin_auth)
    assert analyzed.status_code == 200
    adata = analyzed.json()
    assert adata["diagnosis"] is not None
    assert adata["diagnosis"]["cognitive_gap_type"] == "concept_confusion"
    assert len(adata["diagnosis"]["solutions"]) == 3

    # 6. 管理员选定方案 opt_2 + 备注，并验证 Level 2 透出到学生端 wrong-attempts（且不泄参考答案）
    assert client.post(
        f"/api/admin/wrong-diagnostics/{wrong_id}/select-solution",
        json={"option_id": "opt_9"},
        headers=admin_auth,
    ).status_code == 422

    selected = client.post(
        f"/api/admin/wrong-diagnostics/{wrong_id}/select-solution",
        json={"option_id": "opt_2", "admin_note": "今晚先用红笔圈出移项符号练习 5 分钟"},
        headers=admin_auth,
    )
    assert selected.status_code == 200
    assert selected.json()["diagnosis"]["selected_option_id"] == "opt_2"
    assert selected.json()["diagnosis"]["admin_note"] == "今晚先用红笔圈出移项符号练习 5 分钟"

    # 学生端历史错题回顾透出 adopted_solution 与错答/正解对照（做题中与刚交卷仍不提前泄答）
    student_wrongs = client.get("/api/practice/wrong-attempts?subject=math", headers=student_auth)
    assert student_wrongs.status_code == 200
    wlist = student_wrongs.json()
    assert len(wlist) == 1
    assert wlist[0]["student_answer"] == "B"
    assert wlist[0]["correct_answer"] == "A"
    assert wlist[0]["adopted_solution"] is not None
    assert wlist[0]["adopted_solution"]["option_id"] == "opt_2"
    assert wlist[0]["adopted_solution"]["title"] == "移项符号双色圈画法"
    assert wlist[0]["adopted_solution"]["admin_note"] == "今晚先用红笔圈出移项符号练习 5 分钟"


def test_ai_tutor_socks_proxy_import_error_fallback(monkeypatch):
    """回归：宿主机存在 socks5 环境变量但缺 socksio 时，_post_chat_completion 必须回退 trust_env=False 而非抛 ImportError(500)。"""
    import json as json_lib

    monkeypatch.setenv("SHUTONG_AI_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("SHUTONG_AI_BASE_URL", "https://api.deepseek.com")

    calls: list[bool] = []
    valid_json = json_lib.dumps(
        {
            "cognitive_gap_type": "condition_omission",
            "root_cause_summary": "审题遗漏限定条件。",
            "evidence_from_dialogue": "学生未列出条件约束。",
            "solutions": [
                {"option_id": "opt_1", "title": "方案1", "approach_focus": "审题", "rationale": "r1", "action_steps": ["s1"]},
                {"option_id": "opt_2", "title": "方案2", "approach_focus": "概念", "rationale": "r2", "action_steps": ["s2"]},
                {"option_id": "opt_3", "title": "方案3", "approach_focus": "变式", "rationale": "r3", "action_steps": ["s3"]},
            ],
        },
        ensure_ascii=False,
    )

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"model": "deepseek-chat", "choices": [{"message": {"content": valid_json}}]}

    class ProxyFailingClient:
        def __init__(self, *args, **kwargs):
            trust_env = kwargs.get("trust_env", True)
            calls.append(trust_env)
            if trust_env:
                raise ImportError("Using SOCKS proxy, but the 'socksio' package is not installed.")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr(ai_tutor.httpx, "Client", ProxyFailingClient)

    parsed, model_used = ai_tutor.request_error_root_cause_analysis(
        subject="math",
        stem="测试题干",
        choices=["A. 1", "B. 2"],
        correct_answer="A",
        student_answer="B",
        knowledge_titles=["实数"],
        dialogue_turns=[],
    )
    assert calls == [True, False]
    assert model_used == "deepseek-chat"
    assert len(parsed["solutions"]) == 3


def test_safe_stem_excerpt_preserves_latex_pairs():
    """正例：公式横跨截断长度时延展至闭合 $，不产生奇数个 $ 导致前端乱码。"""
    from shutong.learning_api import _safe_stem_excerpt

    stem = "方程组 $\\begin{cases} x - y = 3 \\\\ 3x - 8y = 14 \\end{cases}$ 的解为（    ）且满足额外条件"
    excerpt = _safe_stem_excerpt(stem, max_len=24)
    assert excerpt.count("$") % 2 == 0
    assert "\\end{cases}$" in excerpt


def test_knowledge_game_config_admin_control_and_student_isolation(client, admin_auth, student_auth):
    """正反例：管理端可配置各科双游戏开关/护盾/闭环与递增 reset_epoch，学生端只读且越权写返回 403。"""
    # 默认值读取（学生端与管理端隔离凭据各自可访问对应只读接口）
    s_default = client.get("/api/knowledge/game-config", headers=student_auth)
    assert s_default.status_code == 200
    math_cfg = s_default.json()["subjects"]["math"]
    assert math_cfg["alchemy_enabled"] is True
    assert math_cfg["expedition_enabled"] is True
    assert math_cfg["initial_shields"] == 3
    assert math_cfg["reset_epoch"] == 0

    # 反例：学生令牌越权访问管理端接口或写入接口 -> 403；管理端令牌误用学生接口 -> 403
    assert client.get("/api/admin/knowledge/game-config", headers=student_auth).status_code == 403
    assert (
        client.put(
            "/api/admin/knowledge/game-config/math",
            json={"alchemy_enabled": False},
            headers=student_auth,
        ).status_code
        == 403
    )
    assert client.get("/api/knowledge/game-config", headers=admin_auth).status_code == 403

    # 正例：管理端更新物理游戏配置并递增 reset_epoch
    updated = client.put(
        "/api/admin/knowledge/game-config/physics",
        json={
            "alchemy_enabled": True,
            "expedition_enabled": False,
            "initial_shields": 2,
            "prioritize_weak": False,
            "practice_gate": "required",
            "increment_reset_epoch": True,
        },
        headers=admin_auth,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["subject"] == "physics"
    assert body["expedition_enabled"] is False
    assert body["initial_shields"] == 2
    assert body["prioritize_weak"] is False
    assert body["practice_gate"] == "required"
    assert body["reset_epoch"] == 1

    # 学生端实时可见更新，且其它学科保持隔离默认
    s_after = client.get("/api/knowledge/game-config", headers=student_auth)
    assert s_after.status_code == 200
    assert s_after.json()["subjects"]["physics"]["expedition_enabled"] is False
    assert s_after.json()["subjects"]["physics"]["reset_epoch"] == 1
    assert s_after.json()["subjects"]["math"]["expedition_enabled"] is True

    # 反例：非法护盾数（4）或未知学科被 422 拦截
    assert (
        client.put(
            "/api/admin/knowledge/game-config/math",
            json={"initial_shields": 4},
            headers=admin_auth,
        ).status_code
        == 422
    )
