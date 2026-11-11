"""
ST-019-D 四科集成技术验收专项测试套件：
补齐 D0 差异盘点识别的四项联合集成断言缺口（第1轮审核整改闭环版）：
- D-T01: 四科共存与学科隔离（同库四科初始化、合法关联、跨学科非法关联拒绝、单科学科操作零污染）
- D-T02: 历史数据与学生证据保护（建立真实存量历史知识点节点及题目关联，验证旧节点不删除、node_version不变、学生作答不被改写，新候选v1->v2重置为pending）
- D-T03: 管理与学生业务链路隔离（角色鉴权隔离、未审批数据边界、多学科学生练习链路防污染）
- D-T04: 四科联合发布与迁移兼容性（四科同库135节点初始化、发布互不串扰、完整快照深度相等、Alembic 正向升级数据保留与降级破坏性回退验证）
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from shutong import models as m
from shutong.database import get_db
from shutong.main import app


def _make_source(client, auth: dict, subject: str, title: str) -> str:
    """创建测试用题源文档。"""
    resp = client.post(
        "/api/admin/sources",
        headers=auth,
        json={
            "title": title,
            "subject": subject,
            "rights_status": "personal_use_reviewed",
            "verified": True,
        },
    )
    assert resp.status_code == 201, f"创建题源失败: {resp.text}"
    return resp.json()["id"]


def _make_and_publish_question(client, auth: dict, source_id: str, stem: str, knowledge_id: str) -> str:
    """创建、审核并发布一道客观题目，返回 question_version_id。"""
    resp = client.post(
        "/api/admin/questions",
        headers=auth,
        json={
            "source_document_id": source_id,
            "stem": stem,
            "kind": "single_choice",
            "options": ["A. 正确", "B. 错误"],
            "correct_answer": "A",
            "knowledge_ids": [knowledge_id],
            "max_points": 2.0,
        },
    )
    assert resp.status_code == 201, f"创建题目失败: {resp.text}"
    version_id = resp.json()["id"]
    rev_resp = client.post(f"/api/admin/questions/{version_id}/review", headers=auth)
    assert rev_resp.status_code == 200, f"审核题目失败: {rev_resp.text}"
    pub_resp = client.post(f"/api/admin/questions/{version_id}/publish", headers=auth)
    assert pub_resp.status_code == 200, f"发布题目失败: {pub_resp.text}"
    return version_id


def test_d_t01_four_subjects_coexistence_and_subject_isolation(client, admin_auth):
    """
    D-T01: 四科共存与学科隔离集成测试。
    1. 同一隔离数据库同时初始化四科（语文25、数学48、英语28、物理34，共135候选）；
    2. 验证四科候选编码与归属正确无混淆；
    3. 验证四科各自合法的本学科题目-知识点关联创建成功；
    4. 验证跨学科非法关联（语数、英物、数语、物英）均被 422 SUBJECT_MISMATCH 强行拒绝；
    5. 对单科（英语）进行候选版本修订与审核状态更新，断言其余三科候选数量、版本及状态零污染。
    """
    subjects = ["chinese", "math", "english", "physics"]
    expected_counts = {"chinese": 25, "math": 48, "english": 28, "physics": 34}

    # 1. 在同一个测试库中同时初始化四科候选
    seeded_nodes = {}
    for subj in subjects:
        seed_resp = client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
        assert seed_resp.status_code == 201, f"{subj} 初始化种子失败: {seed_resp.text}"
        assert seed_resp.json()["seeded_count"] == expected_counts[subj]

        cands = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth).json()
        assert len(cands) == expected_counts[subj], f"{subj} 候选数量不符预期"
        prefix = f"{subj}_cand."
        db_session = next(app.dependency_overrides[get_db]())
        for c in cands:
            assert c["code"].startswith(prefix), f"节点编码 {c['code']} 必须以 {prefix} 开头"
            node_entity = db_session.get(m.KnowledgeNode, c["id"])
            assert node_entity is not None
            assert node_entity.subject == subj
            assert c["is_seeded"] is True
            assert c["review_status"] == "pending"
        seeded_nodes[subj] = cands

    # 验证同库中活跃候选节点总数为 135
    total_active_cands = sum(len(cands) for cands in seeded_nodes.values())
    assert total_active_cands == 135, f"四科总候选数期望 135，实际 {total_active_cands}"

    # 2. 为四科各创建一道本学科题目
    question_versions = {}
    for subj in subjects:
        src_id = _make_source(client, admin_auth, subj, f"虚构测试：{subj}试题来源")
        first_node = seeded_nodes[subj][0]
        qv_id = _make_and_publish_question(client, admin_auth, src_id, f"虚构测试：{subj}题目内容", first_node["code"])
        question_versions[subj] = qv_id

        # 3. 验证本学科合法关联 (201)
        link_resp = client.post(
            "/api/admin/knowledge/links",
            headers=admin_auth,
            json={
                "question_version_id": qv_id,
                "node_id": first_node["id"],
                "role": "core",
                "evidence": f"合法的 {subj} 知识点关联依据",
            },
        )
        assert link_resp.status_code == 201, f"本学科合法关联失败: {link_resp.text}"
        assert link_resp.json()["node_version"] == 1

    # 4. 验证跨学科非法关联全部被 422 拒绝（正反例多对）
    cross_pairs = [
        ("chinese", "math"),      # 语文题目 -> 数学知识点
        ("english", "physics"),   # 英语题目 -> 物理知识点
        ("math", "chinese"),      # 数学题目 -> 语文知识点
        ("physics", "english"),   # 物理题目 -> 英语知识点
    ]
    for q_subj, node_subj in cross_pairs:
        qv = question_versions[q_subj]
        foreign_node = seeded_nodes[node_subj][0]
        cross_resp = client.post(
            "/api/admin/knowledge/links",
            headers=admin_auth,
            json={
                "question_version_id": qv,
                "node_id": foreign_node["id"],
                "role": "core",
                "evidence": "非法跨学科关联测试",
            },
        )
        assert cross_resp.status_code == 422, f"跨学科关联 ({q_subj} -> {node_subj}) 必须拒绝: {cross_resp.text}"
        assert cross_resp.json()["detail"] == "SUBJECT_MISMATCH"

    # 5. 不变项验证：对英语的一个节点执行版本修订并审核，断言其他三科保持零污染
    eng_node = seeded_nodes["english"][0]
    rev_resp = client.post(
        f"/api/admin/knowledge/nodes/{eng_node['id']}/versions",
        headers=admin_auth,
        json={
            "name": "英语考点修订名称",
            "description": "英语考点修订详细说明",
            "source_clause_ids": eng_node["source_clause_ids"],
        },
    )
    assert rev_resp.status_code == 201
    assert rev_resp.json()["version"] == 2

    # 对英语该节点进行审核（测试模拟数据）
    review_resp = client.post(
        f"/api/admin/knowledge/nodes/{eng_node['id']}/review",
        headers=admin_auth,
        json={
            "reviewer_id": "prof_english_tester",
            "review_status": "approved",
            "review_opinion": "英语修订版本审核通过（测试模拟数据）",
        },
    )
    assert review_resp.status_code == 200

    # 检查其余三科（语文、数学、物理）的状态与版本完全不受影响
    for subj in ["chinese", "math", "physics"]:
        cands_check = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth).json()
        assert len(cands_check) == expected_counts[subj], f"{subj} 候选数量遭到篡改"
        for c in cands_check:
            assert c["review_status"] == "pending", f"{subj} 节点 {c['code']} 审核状态被异常修改"
            assert c["version"] == 1, f"{subj} 节点 {c['code']} 版本号被异常递增"


def test_d_t02_historical_data_and_student_evidence_protection(client, admin_auth, student_auth):
    """
    D-T02: 历史数据与学生证据保护集成测试（B2 补足真实历史旧知识点断言）。
    1. 在隔离库中建立真实存量历史知识点（math.arithmetic）及题目关联，产生学生作答记录 (AnswerAttempt)；
    2. 建立新候选知识点题目并关联版本1，产生新题作答记录；
    3. 执行知识点生命周期演进：新候选节点产生版本2、存量历史知识点执行停用 (deprecated)；
    4. 断言历史旧节点未被物理删除，状态正确置为 deprecated；
    5. 断言题目关联引用的 node_version 依然为 1，绝不被静默升级为 2；
    6. 断言学生已有作答记录与得分（历史题与新题）未被改写；
    7. 断言新候选版本2审核状态重置为 pending，不继承版本1审核；
    8. 断言存量81个历史考点映射契约保持只读完整性。
    """
    # 1. 建立存量历史旧知识点节点（math.arithmetic）
    leg_node_resp = client.post(
        "/api/admin/knowledge/nodes",
        headers=admin_auth,
        json={
            "subject": "math",
            "code": "math.arithmetic",
            "name": "基础算术（存量历史考点）",
            "origin": "manual",
        },
    )
    assert leg_node_resp.status_code == 201
    leg_node_id = leg_node_resp.json()["id"]

    # 审核历史节点版本1通过（测试模拟数据）
    rev_leg = client.post(
        f"/api/admin/knowledge/nodes/{leg_node_id}/review",
        headers=admin_auth,
        json={
            "reviewer_id": "prof_legacy_auditor",
            "review_status": "approved",
            "review_opinion": "历史考点初审通过（测试模拟数据）",
        },
    )
    assert rev_leg.status_code == 200

    # 建立历史题源、题目并发布
    src_leg_id = _make_source(client, admin_auth, "math", "虚构测试：存量历史题源")
    qv_leg_id = _make_and_publish_question(client, admin_auth, src_leg_id, "虚构测试：历史算术题 1+1=?", "math.arithmetic")

    # 关联历史题目与历史节点版本1
    link_leg_resp = client.post(
        "/api/admin/knowledge/links",
        headers=admin_auth,
        json={
            "question_version_id": qv_leg_id,
            "node_id": leg_node_id,
            "role": "core",
            "evidence": "历史考点初版关联依据",
        },
    )
    assert link_leg_resp.status_code == 201
    assert link_leg_resp.json()["node_version"] == 1

    # 学生练习出题并提交历史题目作答
    next_leg_resp = client.get("/api/practice/next?subject=math", headers=student_auth)
    assert next_leg_resp.status_code == 200
    item_leg = next_leg_resp.json()
    assert item_leg["question_version_id"] == qv_leg_id

    client_attempt_id_leg = "st019d-legacy-attempt-key-001"
    att_leg_resp = client.post(
        "/api/practice/attempts",
        headers=student_auth,
        json={
            "client_attempt_id": client_attempt_id_leg,
            "exposure_id": item_leg["exposure_id"],
            "answer": "A",
        },
    )
    assert att_leg_resp.status_code == 201
    saved_leg_attempt_id = att_leg_resp.json()["id"]
    saved_leg_earned_points = att_leg_resp.json()["earned_points"]
    assert saved_leg_earned_points == 2.0

    # 2. 种子初始化数学候选节点
    client.post("/api/admin/knowledge/candidates/seed?subject=math", headers=admin_auth)
    cands = client.get("/api/admin/knowledge/candidates?subject=math", headers=admin_auth).json()
    target_cand_node = cands[0]
    cand_node_id = target_cand_node["id"]

    # 审核新候选节点版本1通过（测试模拟数据）
    rev1 = client.post(
        f"/api/admin/knowledge/nodes/{cand_node_id}/review",
        headers=admin_auth,
        json={
            "reviewer_id": "prof_math_v1",
            "review_status": "approved",
            "review_opinion": "候选版本1初审通过（测试模拟数据）",
        },
    )
    assert rev1.status_code == 200

    # 建立题源、题目并发布新题
    src_cand_id = _make_source(client, admin_auth, "math", "虚构测试：数学新版题源")
    qv_cand_id = _make_and_publish_question(client, admin_auth, src_cand_id, "虚构测试：代数新题", target_cand_node["code"])

    # 关联新题目与候选版本1
    link_cand_resp = client.post(
        "/api/admin/knowledge/links",
        headers=admin_auth,
        json={
            "question_version_id": qv_cand_id,
            "node_id": cand_node_id,
            "role": "core",
            "evidence": "新候选初版关联依据",
        },
    )
    assert link_cand_resp.status_code == 201
    assert link_cand_resp.json()["node_version"] == 1

    # 学生练习出题并提交新题目作答
    next_cand_resp = client.get("/api/practice/next?subject=math", headers=student_auth)
    assert next_cand_resp.status_code == 200
    item_cand = next_cand_resp.json()
    assert item_cand["question_version_id"] == qv_cand_id

    client_attempt_id_cand = "st019d-cand-attempt-key-001"
    att_cand_resp = client.post(
        "/api/practice/attempts",
        headers=student_auth,
        json={
            "client_attempt_id": client_attempt_id_cand,
            "exposure_id": item_cand["exposure_id"],
            "answer": "A",
        },
    )
    assert att_cand_resp.status_code == 201
    saved_cand_attempt_id = att_cand_resp.json()["id"]
    saved_cand_earned_points = att_cand_resp.json()["earned_points"]
    assert saved_cand_earned_points == 2.0

    # 3. 执行生命周期演进：新候选节点产生版本2、存量历史知识点执行停用 (deprecated)
    rev2_resp = client.post(
        f"/api/admin/knowledge/nodes/{cand_node_id}/versions",
        headers=admin_auth,
        json={
            "name": f"{target_cand_node['name']}（修订版）",
            "description": "这是后续修订的新版知识点说明",
            "source_clause_ids": target_cand_node["source_clause_ids"],
        },
    )
    assert rev2_resp.status_code == 201
    assert rev2_resp.json()["version"] == 2

    # 停用历史存量节点
    dep_leg_resp = client.post(f"/api/admin/knowledge/nodes/{leg_node_id}/deprecate", headers=admin_auth)
    assert dep_leg_resp.status_code == 200
    assert dep_leg_resp.json()["status"] == "deprecated"

    # 停用另一个数学候选节点
    other_cand_node = cands[1]
    dep_cand_resp = client.post(f"/api/admin/knowledge/nodes/{other_cand_node['id']}/deprecate", headers=admin_auth)
    assert dep_cand_resp.status_code == 200
    assert dep_cand_resp.json()["status"] == "deprecated"

    # 4. 历史数据与学生作答证据不变项校验
    db = next(app.dependency_overrides[get_db]())

    # 不变项 1：历史旧节点未被物理删除，状态正确记录为 deprecated
    leg_node_db = db.get(m.KnowledgeNode, leg_node_id)
    assert leg_node_db is not None
    assert leg_node_db.status == "deprecated"

    # 不变项 2：历史题目关联合约引用的 node_version 保持为 1，未被修改
    link_leg_db = db.scalar(
        select(m.QuestionKnowledgeLink).where(
            m.QuestionKnowledgeLink.question_version_id == qv_leg_id,
            m.QuestionKnowledgeLink.node_id == leg_node_id,
        )
    )
    assert link_leg_db is not None
    assert link_leg_db.node_version == 1, f"历史题目关联必须锁定当时的 node_version=1，实际: {link_leg_db.node_version}"

    # 不变项 3：学生历史答题记录 (AnswerAttempt) 内容与得分完全未被改写
    att_leg_db = db.get(m.AnswerAttempt, saved_leg_attempt_id)
    assert att_leg_db is not None
    assert att_leg_db.client_attempt_id == client_attempt_id_leg
    assert att_leg_db.earned_points == saved_leg_earned_points
    assert att_leg_db.answer == "A"

    # 不变项 4：新候选节点的题目关联保持 node_version=1
    link_cand_db = db.scalar(
        select(m.QuestionKnowledgeLink).where(
            m.QuestionKnowledgeLink.question_version_id == qv_cand_id,
            m.QuestionKnowledgeLink.node_id == cand_node_id,
        )
    )
    assert link_cand_db is not None
    assert link_cand_db.node_version == 1, f"新候选题目关联必须锁定当时的 node_version=1，实际: {link_cand_db.node_version}"

    # 不变项 5：新题目学生作答记录 (AnswerAttempt) 保持原值
    att_cand_db = db.get(m.AnswerAttempt, saved_cand_attempt_id)
    assert att_cand_db is not None
    assert att_cand_db.client_attempt_id == client_attempt_id_cand
    assert att_cand_db.earned_points == saved_cand_earned_points
    assert att_cand_db.answer == "A"

    # 不变项 6：新候选版本2重置为 pending，未继承版本1的 approved
    v2_db = db.scalar(
        select(m.KnowledgeNodeVersion).where(
            m.KnowledgeNodeVersion.node_id == cand_node_id,
            m.KnowledgeNodeVersion.version == 2,
        )
    )
    assert v2_db is not None
    assert v2_db.review_status == "pending", f"新修订版本必须处于 pending，实际: {v2_db.review_status}"
    assert v2_db.reviewer_id is None, "新修订版本不得继承旧审核人"
    assert v2_db.review_opinion is None, "新修订版本不得继承旧审核意见"

    # 不变项 7：四科存量 81 个历史考点映射契约依然有效可查
    for s, exp_leg_cnt in [("chinese", 18), ("math", 24), ("english", 18), ("physics", 21)]:
        leg_resp = client.get(f"/api/admin/knowledge/legacy-mapping?subject={s}", headers=admin_auth)
        assert leg_resp.status_code == 200
        leg_data = leg_resp.json()
        assert len(leg_data["legacy_mappings"]) == exp_leg_cnt, f"{s} 历史考点映射数量不符"


def test_d_t03_admin_student_business_pipeline_isolation(client, admin_auth, student_auth):
    """
    D-T03: 管理与学生业务链路隔离集成测试。
    1. 学生凭据绝对禁止访问任何管理端知识库接口 (403 Forbidden)；
    2. 待审核 (pending) 知识点边界：未审核候选不能被作为获批知识库对外提供；
    3. 学生端业务链路无敏感审核元数据泄露（无 reviewer_id、review_opinion 等内部字段）；
    4. 多学科共存场景下，学生端取题与练习严格按学科隔离，绝不产生跨学科数据混杂。
    """
    # 1. 权限边界：学生身份访问管理端核心写/读操作一律 403
    assert client.post("/api/admin/knowledge/candidates/seed?subject=chinese", headers=student_auth).status_code == 403
    assert client.post("/api/admin/knowledge/releases", json={"subject": "chinese"}, headers=student_auth).status_code == 403
    assert client.post("/api/admin/knowledge/nodes/fake_id/review", json={}, headers=student_auth).status_code == 403
    assert client.get("/api/admin/knowledge/candidates?subject=chinese", headers=student_auth).status_code == 403
    assert client.get("/api/admin/knowledge/clauses?subject=chinese", headers=student_auth).status_code == 403

    # 2. 未审批数据边界：管理端初始化四科后，候选处于 pending 状态，发布清单中 0 发布
    for s in ["chinese", "math", "english", "physics"]:
        client.post(f"/api/admin/knowledge/candidates/seed?subject={s}", headers=admin_auth)
    rel_resp = client.get("/api/admin/knowledge/releases", headers=admin_auth)
    assert rel_resp.status_code == 200
    assert len(rel_resp.json()) == 0, "未审核发布的候选体系绝不能出现在已发布清单中"

    # 3. 业务链路多学科隔离：创建语文和数学两道正式题目
    src_cn = _make_source(client, admin_auth, "chinese", "虚构测试：语文学科来源")
    src_ma = _make_source(client, admin_auth, "math", "虚构测试：数学学科来源")

    qv_cn = _make_and_publish_question(client, admin_auth, src_cn, "虚构测试：语文古诗文题干", "chinese_cand.reading_ancient")
    qv_ma = _make_and_publish_question(client, admin_auth, src_ma, "虚构测试：数学勾股定理题干", "math_cand.geom_pythagorean")

    # 学生分别按学科取题
    resp_cn = client.get("/api/practice/next?subject=chinese", headers=student_auth)
    assert resp_cn.status_code == 200
    cn_item = resp_cn.json()
    assert cn_item["question_version_id"] == qv_cn
    assert "语文古诗文题干" in cn_item["stem"]
    # 严禁泄露内部知识库元数据
    for forbidden in ["reviewer_id", "review_opinion", "knowledge_ids", "knowledge_id", "source_clause_ids"]:
        assert forbidden not in cn_item, f"学生端接口严禁泄露管理元数据字段 {forbidden}"

    resp_ma = client.get("/api/practice/next?subject=math", headers=student_auth)
    assert resp_ma.status_code == 200
    ma_item = resp_ma.json()
    assert ma_item["question_version_id"] == qv_ma
    assert "数学勾股定理题干" in ma_item["stem"]
    assert "语文古诗文题干" not in ma_item["stem"], "学生取数学题绝不能混入语文题目"


def test_d_t04_four_subjects_joint_release_and_migration_compatibility(client, admin_auth, tmp_path):
    """
    D-T04: 四科联合发布与迁移兼容性集成测试（B1 纠正迁移无损证明，B2 补足四科135节点及深度快照比对）。
    1. 同一测试库初始化四科候选（合计135个），存在未审核候选的学科（英语）发布正式版本被强行拒绝 (400)；
    2. 全量审核通过的学科（语文）发布正式版本成功 (201)，生成完整不可变历史快照；
    3. 随后对未发布学科（英语）进行候选节点演变，已发布的语文学科快照保持绝对深度相等；
    4. Alembic 迁移验证：正向升级完整保留历史数据，架构降级为丢弃新增表数据的破坏性回退，再次升级通过一致性检查。
    """
    # 1. 在同一个测试库中同时初始化四科候选
    for s in ["chinese", "math", "english", "physics"]:
        seed_resp = client.post(f"/api/admin/knowledge/candidates/seed?subject={s}", headers=admin_auth)
        assert seed_resp.status_code == 201

    # 验证四科在同一测试数据库中全部初始化，总数精确等于 135
    total_cands = sum(
        len(client.get(f"/api/admin/knowledge/candidates?subject={s}", headers=admin_auth).json())
        for s in ["chinese", "math", "english", "physics"]
    )
    assert total_cands == 135, f"四科总候选数期望 135，实际 {total_cands}"

    # 负例：英语候选处于 pending，尝试发布英语正式版本 -> 400 强行拒绝
    pub_eng_bad = client.post(
        "/api/admin/knowledge/releases",
        headers=admin_auth,
        json={
            "subject": "english",
            "release_version": "english-st019d-fail-attempt",
            "published_by": "test_director",
            "summary": "尝试未审核发布英语（测试模拟数据）",
        },
    )
    assert pub_eng_bad.status_code == 400
    assert "存在未审核或已驳回的候选知识点" in pub_eng_bad.json()["detail"]

    # 2. 对语文学科全量 25 个候选节点执行模拟审核通过（测试模拟数据）
    cn_cands = client.get("/api/admin/knowledge/candidates?subject=chinese", headers=admin_auth).json()
    assert len(cn_cands) == 25
    for c in cn_cands:
        r_resp = client.post(
            f"/api/admin/knowledge/nodes/{c['id']}/review",
            headers=admin_auth,
            json={
                "reviewer_id": "prof_chinese_joint_test",
                "review_status": "approved",
                "review_opinion": "经核验课标与考点划分一致，准予通过（测试模拟数据）",
            },
        )
        assert r_resp.status_code == 200

    # 正式发布语文版本
    cn_release_ver = "chinese-st019d-v2022.1.0"
    pub_cn_resp = client.post(
        "/api/admin/knowledge/releases",
        headers=admin_auth,
        json={
            "subject": "chinese",
            "release_version": cn_release_ver,
            "published_by": "admin_director",
            "summary": "语文官方课标知识库联合集成发布版本（测试模拟数据）",
        },
    )
    assert pub_cn_resp.status_code == 201, f"发布语文正式版本失败: {pub_cn_resp.text}"
    cn_pub_data = pub_cn_resp.json()
    assert cn_pub_data["subject"] == "chinese"
    assert cn_pub_data["release_version"] == cn_release_ver
    assert cn_pub_data["status"] == "published"
    assert cn_pub_data["total_nodes"] == 25
    assert cn_pub_data["curriculum_source_id"] is not None

    # 保存演变前语文已发布版本的完整 snapshot 深度副本
    db_session = next(app.dependency_overrides[get_db]())
    db_release = db_session.scalar(
        select(m.KnowledgeTaxonomyRelease).where(m.KnowledgeTaxonomyRelease.release_version == cn_release_ver)
    )
    assert db_release is not None
    saved_snapshot = copy.deepcopy(db_release.snapshot)
    assert saved_snapshot["total_nodes"] == 25
    assert len(saved_snapshot["nodes"]) == 25

    # 3. 对未发布的英语候选执行修改与演变
    eng_cands = client.get("/api/admin/knowledge/candidates?subject=english", headers=admin_auth).json()
    eng_rev = client.post(
        f"/api/admin/knowledge/nodes/{eng_cands[0]['id']}/versions",
        headers=admin_auth,
        json={
            "name": "英语考点独立修订",
            "description": "英语考点演变说明",
            "source_clause_ids": eng_cands[0]["source_clause_ids"],
        },
    )
    assert eng_rev.status_code == 201

    # 验证语文学科的已发布快照保持绝对深度相等（包含全量节点列表、元数据等完全一致）
    releases = client.get("/api/admin/knowledge/releases?subject=chinese", headers=admin_auth).json()
    assert len(releases) == 1
    rel = releases[0]
    assert rel["release_version"] == cn_release_ver
    assert rel["total_nodes"] == 25
    db_session.refresh(db_release)
    assert db_release.snapshot == saved_snapshot, "英语候选演变后，已发布的语文快照必须保持绝对深度相等"

    # 4. Alembic 迁移验证：正向升级保留历史数据、降级具备破坏性回退能力并再次升级通过
    api_dir = Path(__file__).resolve().parents[1]
    mig_db_path = tmp_path / "st019d_migration.sqlite3"
    url = f"sqlite+pysqlite:///{mig_db_path}"
    mig_env = dict(os.environ, DATABASE_URL=url)

    def run_alembic(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=api_dir,
            env=mig_env,
            check=True,
            capture_output=True,
            text=True,
        )

    # 步骤 4.1：升级至 0006，写入存量历史数据
    run_alembic("upgrade", "0006")
    mig_engine = create_engine(url)
    with mig_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_nodes (id, subject, code, status, created_at) "
                "VALUES ('mig_legacy_kn_1', 'math', 'math.legacy.test01', 'active', CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO knowledge_node_versions (id, node_id, version, name, origin, review_status, created_at) "
                "VALUES ('mig_legacy_knv_1', 'mig_legacy_kn_1', 1, '旧版考点迁移保留测试', 'manual', 'approved', CURRENT_TIMESTAMP)"
            )
        )

    # 步骤 4.2：正向升级至 head (执行 0007 与 0008 迁移)，验证存量数据完整保留
    run_alembic("upgrade", "head")
    run_alembic("check")

    with mig_engine.begin() as conn:
        kn_row = conn.execute(text("SELECT id, code, status FROM knowledge_nodes WHERE id='mig_legacy_kn_1'")).one()
        assert kn_row == ("mig_legacy_kn_1", "math.legacy.test01", "active")

        knv_row = conn.execute(
            text("SELECT id, name, parent_code, source_clause_ids, reviewer_id FROM knowledge_node_versions WHERE id='mig_legacy_knv_1'")
        ).one()
        assert knv_row[0] == "mig_legacy_knv_1"
        assert knv_row[1] == "旧版考点迁移保留测试"
        assert knv_row[2] == "UNKNOWN", "0008 迁移脚本必须将历史存量版本 parent_code 回填为 UNKNOWN"
        assert knv_row[3] is None

    # 校验 head 新增表与列结构健全
    insp = inspect(mig_engine)
    assert "knowledge_taxonomy_releases" in insp.get_table_names()
    knv_cols = {c["name"] for c in insp.get_columns("knowledge_node_versions")}
    assert {"source_clause_ids", "reviewer_id", "review_opinion", "reviewed_at"} <= knv_cols
    assert {"parent_node_id", "parent_code"} <= knv_cols

    # 步骤 4.3：降级到 0006。
    # 明确验证：0007 降级脚本按设计会物理 DROP knowledge_taxonomy_releases 表，
    # 因此降级属于丢弃新增表数据的破坏性架构降级（Destructive Downgrade），在此如实验证其架构回退行为。
    with mig_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_taxonomy_releases (id, subject, release_version, status, snapshot, created_at) "
                "VALUES ('rel-test-01', 'physics', 'phy-v1', 'published', '{}', CURRENT_TIMESTAMP)"
            )
        )
    run_alembic("downgrade", "0006")
    insp_down = inspect(mig_engine)
    assert "knowledge_taxonomy_releases" not in insp_down.get_table_names()

    # 步骤 4.4：再次正向升级至 head，验证迁移幂等性与模式一致性无残留
    run_alembic("upgrade", "head")
    run_alembic("check")
    mig_engine.dispose()


def test_st020_2b02_conservation_and_safeguards():
    """
    ST-020-2B-02 全局守恒与权限安全护栏断言：
    1. 候选知识点总数严格守恒为 135（语文25、数学48、英语28、物理34）；
    2. 课标条款总数严格守恒为 312（语文34、数学150、英语30、物理98）；
    3. 存量考点字典严格守恒为 81（语文18、数学24、英语18、物理21）；
    4. 审核发布状态安全：全量 135 候选与 312 条款 100% 保持 pending 初始状态，无越权发布；
    5. 幽灵旧码清零安全：四科候选与条款中幽灵旧码严格为 0；
    6. 独立映射契约合法性：四科映射表中所有 target_candidate_codes 必须在 135 候选中真实存在。
    """
    import json
    from shutong.corpus.taxonomy import TAXONOMY

    root_dir = Path(__file__).resolve().parents[3]
    contracts_dir = root_dir / "contracts"

    # 1. 候选总数守恒
    expected_cands = {"chinese": 25, "math": 48, "english": 28, "physics": 34}
    total_cands = 0
    all_cand_codes = set()
    for subj, exp_count in expected_cands.items():
        c_path = contracts_dir / f"{subj}_knowledge_taxonomy_candidate.json"
        cands = json.loads(c_path.read_text(encoding="utf-8"))
        assert len(cands) == exp_count, f"{subj} 候选数量偏离: 期望 {exp_count}, 实际 {len(cands)}"
        total_cands += len(cands)
        for c in cands:
            all_cand_codes.add(c["code"])
            assert c["review_status"] == "pending", f"候选 {c['code']} 状态异常: {c['review_status']}"
    assert total_cands == 135, f"四科候选总数必须为 135，实际: {total_cands}"

    # 2. 条款总数守恒
    expected_clauses = {"chinese": 34, "math": 150, "english": 30, "physics": 98}
    total_clauses = 0
    for subj, exp_count in expected_clauses.items():
        cl_path = contracts_dir / f"curriculum_clauses_{subj}.json"
        clauses = json.loads(cl_path.read_text(encoding="utf-8"))
        assert len(clauses) == exp_count, f"{subj} 条款数量偏离: 期望 {exp_count}, 实际 {len(clauses)}"
        total_clauses += len(clauses)
        for cl in clauses:
            assert cl["review_status"] == "pending", f"条款 {cl['clause_id']} 状态异常: {cl['review_status']}"
    assert total_clauses == 312, f"四科条款总数必须为 312，实际: {total_clauses}"

    # 3. 存量考点 81 字典守恒
    expected_legacy = {"chinese": 18, "math": 24, "english": 18, "physics": 21}
    total_legacy = 0
    for subj, exp_count in expected_legacy.items():
        actual_count = len(TAXONOMY.get(subj, []))
        assert actual_count == exp_count, f"{subj} 存量考点数量偏离: 期望 {exp_count}, 实际 {actual_count}"
        total_legacy += actual_count
    assert total_legacy == 81, f"存量考点总盘必须为 81，实际: {total_legacy}"

    # 4. 幽灵旧码清零断言
    for subj in ["chinese", "math", "english", "physics"]:
        valid_codes = {n["code"] for n in TAXONOMY.get(subj, [])}
        c_path = contracts_dir / f"{subj}_knowledge_taxonomy_candidate.json"
        cands = json.loads(c_path.read_text(encoding="utf-8"))
        for c in cands:
            lms = c.get("legacy_mapping_codes") or c.get("legacy_mappings") or []
            for lm in lms:
                assert lm in valid_codes, f"{subj} 候选 {c['code']} 包含非法幽灵码: {lm}"

        cl_path = contracts_dir / f"curriculum_clauses_{subj}.json"
        clauses = json.loads(cl_path.read_text(encoding="utf-8"))
        for cl in clauses:
            for lm in cl.get("legacy_mappings", []):
                assert lm in valid_codes, f"{subj} 条款 {cl['clause_id']} 包含非法幽灵码: {lm}"

    # 5. 映射表目标候选存在性断言
    for subj in ["chinese", "math", "english", "physics"]:
        m_path = contracts_dir / f"{subj}_legacy_taxonomy_mapping.json"
        m_data = json.loads(m_path.read_text(encoding="utf-8"))
        for entry in m_data.get("legacy_mappings", []):
            for tc in entry.get("target_candidate_codes", []):
                assert tc in all_cand_codes, f"{subj} 映射表旧考点 {entry['legacy_code']} 指向未知候选节点: {tc}"
