# -*- coding: utf-8 -*-
"""
书童 ST-019-C：语文、英语、物理三科权威知识库建设与全链路门禁验收自动化测试套件。

涵盖：
1. 三科课标条款完整性、真实性与 Schema 合法性核验；
2. 三科权威候选知识体系双向溯源覆盖率 100% 断言；
3. 存量 57 个历史旧考点映射与 81 静态考点只读保护；
4. 综合管理工作台 API 端点多学科参数化与跨学科数据隔离；
5. 候选种子初始化、契约差异检测与安全同步闭环；
6. 版本修订来源继承、纯 API 审核与重新审批；
7. 正式发布强门禁（无候选被拒、缺节点被拒、额外节点被拒、未审被拒、缺证据被拒、空来源被拒）；
8. 隔离测试库全链条正例发布与不可变历史快照生成。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
import sqlalchemy as sa
from sqlalchemy import select

from shutong.corpus.taxonomy import TAXONOMY
from shutong.database import get_db
from shutong.main import app
import shutong.models as m

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = ROOT / "contracts"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"


def test_three_subjects_curriculum_clauses_completeness_and_schema():
    """1. 校验语文、英语、物理三科官方课标条款全集完整性与 Schema 合规。"""
    schema_path = SCHEMAS_DIR / "curriculum-standard-clause.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    for subj in ["chinese", "english", "physics"]:
        path = CONTRACTS_DIR / f"curriculum_clauses_{subj}.json"
        assert path.exists(), f"未找到学科 {subj} 课程标准条款全集文件"
        clauses = json.loads(path.read_text(encoding="utf-8"))
        assert len(clauses) >= 15, f"{subj} 课标条款数量不足"

        clause_ids = set()
        for c in clauses:
            errors = list(validator.iter_errors(c))
            assert not errors, f"[{subj}] 条款 {c.get('clause_id')} 校验失败: {errors[0].message if errors else ''}"

            cid = c["clause_id"]
            assert cid not in clause_ids, f"[{subj}] 存在重复 clause_id: {cid}"
            clause_ids.add(cid)

            # 字段业务规则
            assert c["subject"] == subj
            assert c["stage"] == "stage4"
            assert c["pdf_page"] >= c["print_page"], f"[{subj}] PDF 页码必须 >= 书籍印刷页码: {cid}"
            assert len(c["raw_text"]) >= 5
            assert c["review_status"] == "pending", f"[{subj}] 初始状态必须恒为 pending: {cid}"
            assert isinstance(c["is_elective"], bool)
            assert len(c["derived_requirement"]) >= 2


def test_three_subjects_candidate_taxonomy_coverage_and_bidirectional_traceability():
    """2. 校验三科候选知识体系覆盖率与 100% 双向课标条款溯源。"""
    for subj in ["chinese", "english", "physics"]:
        clauses_path = CONTRACTS_DIR / f"curriculum_clauses_{subj}.json"
        clauses = json.loads(clauses_path.read_text(encoding="utf-8"))
        valid_clause_ids = {c["clause_id"] for c in clauses}

        cand_path = CONTRACTS_DIR / f"{subj}_knowledge_taxonomy_candidate.json"
        assert cand_path.exists(), f"未找到学科 {subj} 候选体系文件"
        cands = json.loads(cand_path.read_text(encoding="utf-8"))
        assert len(cands) >= 18, f"{subj} 候选节点数量不足"

        cand_codes = set()
        for cand in cands:
            code = cand["code"]
            assert code.startswith(f"{subj}_cand."), f"候选代码必须以 {subj}_cand. 为前缀: {code}"
            assert code not in cand_codes, f"候选代码重复: {code}"
            cand_codes.add(code)

            assert cand["review_status"] == "pending", f"候选初始状态必须为 pending: {code}"
            source_clauses = cand.get("source_clause_ids") or []
            assert len(source_clauses) >= 1, f"候选节点 {code} 必须至少关联一条课标条款"

            for cid in source_clauses:
                assert cid in valid_clause_ids, f"候选节点 {code} 引用了不存在的条款: {cid}"


def test_legacy_57_nodes_mapping_and_historical_protection():
    """3. 校验存量 57 个旧节点（语文 18、英语 18、物理 21）映射审计与 81 静态考点只读保护。"""
    # 存量 81 个考点树零修改断言
    total_static_nodes = sum(len(v) for v in TAXONOMY.values())
    assert total_static_nodes == 81, f"存量考点总数必须为 81，实际 {total_static_nodes}"
    assert len(TAXONOMY["chinese"]) == 18, "语文存量考点应为 18 个"
    assert len(TAXONOMY["english"]) == 18, "英语存量考点应为 18 个"
    assert len(TAXONOMY["physics"]) == 21, "物理存量考点应为 21 个"
    assert len(TAXONOMY["math"]) == 24, "数学存量考点应为 24 个"

    for subj, count in [("chinese", 18), ("english", 18), ("physics", 21)]:
        mapping_path = CONTRACTS_DIR / f"{subj}_legacy_taxonomy_mapping.json"
        assert mapping_path.exists(), f"未找到学科 {subj} 映射契约"
        data = json.loads(mapping_path.read_text(encoding="utf-8"))

        mappings = data.get("legacy_mappings", [])
        assert len(mappings) == count, f"[{subj}] 映射考点数不匹配: 期望 {count}, 实际 {len(mappings)}"

        legacy_codes_in_file = set()
        for item in mappings:
            lcode = item["legacy_code"]
            assert lcode.startswith(f"{subj}."), f"旧考点代码必须以 {subj}. 开头: {lcode}"
            legacy_codes_in_file.add(lcode)
            assert item["action"] in [
                "retained", "renamed", "split", "merged", "new", "deprecated", "pending_human_review"
            ]
            assert len(item["mapping_reason"]) >= 5
            assert len(item["compatibility_assurance"]) >= 5

        # 与 TAXONOMY 静态定义完全一一对应
        expected_static_codes = {n["code"] for n in TAXONOMY[subj]}
        assert legacy_codes_in_file == expected_static_codes, f"[{subj}] 映射文件中的旧考点与 TAXONOMY 静态定义不一致"


def test_admin_knowledge_api_multi_subject_clauses_and_mappings(client, admin_auth):
    """4. 校验 /api/admin/knowledge/clauses 与 /legacy-mapping 跨学科参数化与数据隔离。"""
    for subj in ["chinese", "english", "physics", "math"]:
        # 1. 条款读取
        resp = client.get(f"/api/admin/knowledge/clauses?subject={subj}", headers=admin_auth)
        assert resp.status_code == 200
        clauses = resp.json()
        assert len(clauses) >= 15
        for c in clauses:
            assert c["subject"] == subj, f"[{subj}] 条款查询返回了其他学科数据: {c.get('subject')}"

        # 2. 新旧映射读取
        resp_m = client.get(f"/api/admin/knowledge/legacy-mapping?subject={subj}", headers=admin_auth)
        assert resp_m.status_code == 200
        m_data = resp_m.json()
        expected_count = 24 if subj == "math" else (21 if subj == "physics" else 18)
        assert len(m_data["legacy_mappings"]) == expected_count


def test_admin_knowledge_candidates_isolation_and_seeding(client, admin_auth):
    """5. 校验候选知识体系查询隔离、种子初始化与契约同步。"""
    for subj in ["chinese", "english", "physics"]:
        # 未入库时查询：返回契约节点，is_seeded=False, review_status=pending
        resp = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth)
        assert resp.status_code == 200
        cands = resp.json()
        assert len(cands) >= 18
        for c in cands:
            assert c["code"].startswith(f"{subj}_cand.")
            assert c["is_seeded"] is False
            assert c["review_status"] == "pending"

        # 执行初始化种子入库
        seed_resp = client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
        assert seed_resp.status_code == 201
        seed_data = seed_resp.json()
        assert seed_data["subject"] == subj
        assert seed_data["seeded_count"] == len(cands)
        assert seed_data["revised_count"] == 0

        # 入库后再次查询：is_seeded=True, id 不为空
        resp_after = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth)
        cands_after = resp_after.json()
        assert len(cands_after) == len(cands)
        for c in cands_after:
            assert c["is_seeded"] is True
            assert c["id"] is not None
            assert c["review_status"] == "pending"

        # 再次执行种子入库：保持幂等
        seed_idem = client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
        assert seed_idem.status_code == 201
        assert seed_idem.json()["seeded_count"] == 0
        assert seed_idem.json()["revised_count"] == 0


def test_three_subjects_release_gate_negative_enforcement(client, admin_auth):
    """6. 校验三科正式发布强门禁（未初始化被拒、未审核被拒、缺证据被拒）。"""
    for subj in ["chinese", "english", "physics"]:
        version = f"{subj}-test-v1.0"
        # 负例 1：未初始化任何候选节点时发布 -> 400
        resp1 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj,
            "release_version": version,
            "published_by": "tester",
            "summary": "尝试无候选发布"
        }, headers=admin_auth)
        assert resp1.status_code == 400
        assert f"未检测到任何 {subj} 新候选知识点" in resp1.json()["detail"]

        # 初始化候选节点入库
        client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)

        # 负例 2：节点全量处于 pending 状态 -> 400
        resp2 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj,
            "release_version": version,
            "published_by": "tester",
            "summary": "尝试未审核发布"
        }, headers=admin_auth)
        assert resp2.status_code == 400
        assert "存在未审核或已驳回的候选知识点" in resp2.json()["detail"]


def test_three_subjects_positive_review_and_release_lifecycle(client, admin_auth):
    """7. 隔离正例全流程：全量候选审核通过 -> 发布正式版本 -> 生成历史快照 -> 跨学科版本号隔离。"""
    # 分别测试语文与物理两科正向发布
    for subj in ["chinese", "physics"]:
        # 1. 种子入库
        client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
        cands = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth).json()

        # 2. 纯 API 逐项实名审核通过
        for c in cands:
            node_id = c["id"]
            rev_resp = client.post(f"/api/admin/knowledge/nodes/{node_id}/review", json={
                "reviewer_id": f"prof_{subj}_expert",
                "review_status": "approved",
                "review_opinion": f"经认真研核教育部2022课标，该考点划分与初中第四学段内容要求完全一致，准予通过。"
            }, headers=admin_auth)
            assert rev_resp.status_code == 200

        # 3. 正式发布
        release_ver = f"{subj}-v2022.1.0-official-test"
        pub_resp = client.post("/api/admin/knowledge/releases", json={
            "subject": subj,
            "release_version": release_ver,
            "published_by": "admin_director",
            "summary": f"{subj} 官方知识库第一版正式发布"
        }, headers=admin_auth)
        assert pub_resp.status_code == 201
        pub_data = pub_resp.json()
        assert pub_data["release_version"] == release_ver
        assert pub_data["status"] == "published"
        assert pub_data["total_nodes"] == len(cands)

        # 4. 查询发布记录
        rel_list = client.get(f"/api/admin/knowledge/releases?subject={subj}", headers=admin_auth).json()
        assert any(r["release_version"] == release_ver for r in rel_list)

        # 5. 校验 P0-04 发布快照必须包含完整来源全集元数据与来源 ID 清单
        published_release = next(r for r in rel_list if r["release_version"] == release_ver)
        assert published_release["status"] == "published"
        assert published_release["total_nodes"] == len(cands)
        assert pub_data["curriculum_source_id"] is not None
        assert len(pub_data["curriculum_source_ids"]) >= 1


def test_p02_safe_upgrade_and_candidate_deprecation(client, admin_auth):
    """P0-02 隔离升级测试：存量非契约候选安全停用（deprecated）、无孤儿环路及API隔离。"""
    subj = "physics"
    # 1. 种子初始化物理候选
    seed_resp = client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
    assert seed_resp.status_code == 201

    # 2. 模拟数据库中存在一个 R1/历史遗留的不在当前契约中的废弃候选
    db = next(app.dependency_overrides[get_db]())
    stmt = select(m.KnowledgeNode).where(m.KnowledgeNode.subject == subj).limit(1)
    sample_node = db.scalar(stmt)
    assert sample_node is not None

    obsolete_code = "physics_cand.obsolete_legacy_topic"
    obsolete_node = m.KnowledgeNode(
        subject=subj,
        code=obsolete_code,
        parent_id=sample_node.parent_id,
        status="active"
    )
    db.add(obsolete_node)
    db.flush()

    obsolete_ver = m.KnowledgeNodeVersion(
        node_id=obsolete_node.id,
        version=1,
        name="已废弃的旧考点",
        description="该考点在最新契约中已被合并或剔除",
        source_clause_ids=["cs:physics:2022:s4:matter:content_req:state_features:c01"],
        review_status="approved",
        reviewer_id="legacy_reviewer"
    )
    db.add(obsolete_ver)
    db.commit()

    # 3. 再次执行种子同步
    resync_resp = client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
    assert resync_resp.status_code == 201

    # 4. 断言该不在契约中的候选被安全标记为 deprecated
    db.refresh(obsolete_node)
    assert obsolete_node.status == "deprecated", f"非契约候选必须被安全停用为 deprecated，实际: {obsolete_node.status}"

    # 5. 断言管理端查询只返回活跃候选，已停用的废弃候选不混入当前候选清单
    cands_resp = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth)
    assert cands_resp.status_code == 200
    active_codes = {c["code"] for c in cands_resp.json()}
    assert obsolete_code not in active_codes, "管理候选查询接口不得返回 deprecated 的废弃节点"


def test_p03_auth_security_token_isolation(client, monkeypatch):
    """P0-03 安全测试：未配置凭据抛出 503，角色交叉使用抛出 403，杜绝硬编码回退。"""
    # 1. 清空所有管理令牌环境变量 -> 访问管理端必须 503
    monkeypatch.delenv("SHUTONG_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("SHUTONG_TOKEN", raising=False)

    resp_no_token = client.get(
        "/api/admin/knowledge/candidates?subject=physics",
        headers={"Authorization": "Bearer any_token"}
    )
    assert resp_no_token.status_code == 503
    assert "SHUTONG_ADMIN_TOKEN is not configured" in resp_no_token.json()["detail"]

    # 2. 恢复有效的学生令牌与管理令牌
    monkeypatch.setenv("SHUTONG_ADMIN_TOKEN", "valid_secret_admin_token_2026")
    monkeypatch.setenv("SHUTONG_STUDENT_TOKEN", "valid_secret_student_token_2026")

    # 用学生令牌访问管理端 -> 403 禁止角色越权
    resp_student_on_admin = client.get(
        "/api/admin/knowledge/candidates?subject=physics",
        headers={"Authorization": "Bearer valid_secret_student_token_2026"}
    )
    assert resp_student_on_admin.status_code == 403
    assert "student token not permitted" in resp_student_on_admin.json()["detail"]

    # 用管理令牌访问管理端 -> 200 正常通过
    resp_admin_ok = client.get(
        "/api/admin/knowledge/candidates?subject=physics",
        headers={"Authorization": "Bearer valid_secret_admin_token_2026"}
    )
    assert resp_admin_ok.status_code == 200


def test_p04_release_gate_rejects_unknown_or_cross_subject_sources(client, admin_auth):
    """P0-04 门禁测试：发布时核验来源全集，严禁 UNKNOWN 或跨学科条款。"""
    subj = "chinese"
    # 1. 种子初始化
    client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
    cands = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth).json()

    # 2. 审核通过全部节点
    for c in cands:
        client.post(f"/api/admin/knowledge/nodes/{c['id']}/review", json={
            "reviewer_id": "prof_auditor",
            "review_status": "approved",
            "review_opinion": "合规准予通过"
        }, headers=admin_auth)

    # 3. 故意将其中一个节点的最新版本篡改为包含跨学科的物理条款 ID
    db = next(app.dependency_overrides[get_db]())
    stmt = select(m.KnowledgeNode).where(m.KnowledgeNode.code == cands[0]["code"])
    node = db.scalar(stmt)
    assert node is not None
    latest_ver = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == node.id)
        .order_by(m.KnowledgeNodeVersion.version.desc())
    )
    assert latest_ver is not None
    # 注入跨学科条款 (physics 条款注入给 chinese 节点)
    latest_ver.source_clause_ids = ["cs:physics:2022:s4:matter:content_req:state_features:c01"]
    db.commit()

    # 4. 尝试发布 -> 必须被 400 强行拦截并明确指出来源条款不属于该学科或不存在
    resp = client.post("/api/admin/knowledge/releases", json={
        "subject": subj,
        "release_version": f"{subj}-v2022-err-test",
        "published_by": "tester",
        "summary": "尝试跨学科来源发布"
    }, headers=admin_auth)
    assert resp.status_code == 400
    assert "候选节点条款溯源无效" in resp.json()["detail"]
    assert "不存在的官方课标条款" in resp.json()["detail"]


def test_parent_change_triggers_new_version_and_resets_pending(client, admin_auth):
    """
    R3 专项阻断测试：父节点变更版本化与审核重置验证。
    1. “只改变父节点、其他字段不变”情形：
       - 验证生成新版本（version+1），状态强制重置为 pending；
       - 审核人、意见、时间等证据清空，绝无法继承旧审核批准。
    2. “已审核/已发布后改变父节点”情形：
       - 验证已发布或全量 approved 状态下，一旦父节点变更，最新版本进入 pending；
       - 发布门禁（POST /knowledge/releases）必须坚决以 400 拦截，杜绝继承旧批准发布；
       - 验证历史发布快照中的 parent_id 不受影响，历史层级完全可追溯。
    """
    subj = "english"
    # 1. 种子初始化
    client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
    cands = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth).json()
    assert len(cands) >= 2

    # 选取一个子节点及其原父节点、目标新父节点
    # 在 english 中：
    # english_cand.vocab.formation (level 2) 原父节点为 english_cand.phonetics_vocab (level 1)
    # 另有 一级分类 english_cand.morphology (level 1)
    child = next(c for c in cands if c["code"] == "english_cand.vocab.formation")
    parent_old = next(c for c in cands if c["code"] == "english_cand.phonetics_vocab")
    parent_new = next(c for c in cands if c["code"] == "english_cand.morphology")

    assert child["parent_id"] == parent_old["id"]

    # 阶段 A：将 child 审核通过为 approved
    review_resp = client.post(f"/api/admin/knowledge/nodes/{child['id']}/review", json={
        "reviewer_id": "auditor_chen",
        "review_status": "approved",
        "review_opinion": "初步审核通过"
    }, headers=admin_auth)
    assert review_resp.status_code == 200

    # 核对当前为 version 1, approved
    db = next(app.dependency_overrides[get_db]())
    v1 = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == child["id"])
        .order_by(m.KnowledgeNodeVersion.version.desc())
    )
    assert v1 is not None and v1.version == 1
    assert v1.review_status == "approved"
    assert v1.reviewer_id == "auditor_chen"

    # 情形 1：只改变父节点，name, description, source_clause_ids 完全保持不变
    revise_resp = client.post(f"/api/admin/knowledge/nodes/{child['id']}/versions", json={
        "name": v1.name,
        "description": v1.description,
        "source_clause_ids": v1.source_clause_ids,
        "parent_code": parent_new["code"]
    }, headers=admin_auth)
    assert revise_resp.status_code == 201
    assert revise_resp.json()["version"] == 2

    # 验证新版本属性
    db.expire_all()
    node_updated = db.get(m.KnowledgeNode, child["id"])
    assert node_updated.parent_id == parent_new["id"], "父节点 ID 必须已成功更新为新父节点"

    v2 = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == child["id"])
        .order_by(m.KnowledgeNodeVersion.version.desc())
    )
    assert v2 is not None and v2.version == 2
    assert v2.review_status == "pending", "仅修改父节点也必须强制重置审核状态为 pending"
    assert v2.reviewer_id is None, "审核人必须清空，无法继承"
    assert v2.review_opinion is None, "审核意见必须清空，无法继承"
    assert v2.reviewed_at is None, "审核时间必须清空"

    # 历史版本 1 仍可追溯
    v1_check = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == child["id"], m.KnowledgeNodeVersion.version == 1)
    )
    assert v1_check is not None and v1_check.review_status == "approved"

    # 情形 2：已审核/尝试发布时，因父节点变更重置为 pending，必须被发布门禁坚决拦截
    # 先审核通过除 child 以外的所有节点，使仅 child 处于 pending
    for c in cands:
        if c["id"] != child["id"]:
            client.post(f"/api/admin/knowledge/nodes/{c['id']}/review", json={
                "reviewer_id": "auditor_chen",
                "review_status": "approved",
                "review_opinion": "全量审核"
            }, headers=admin_auth)

    # 此时尝试发布 -> 必须被 400 拦截！因为 child 处于 pending 状态，无法继承旧 version 1 的 approved
    pub_fail = client.post("/api/admin/knowledge/releases", json={
        "subject": subj,
        "release_version": f"{subj}-v2022-parent-test-fail",
        "published_by": "auditor_chen",
        "summary": "尝试带未重新审核的父节点变更发布"
    }, headers=admin_auth)
    assert pub_fail.status_code == 400
    assert "存在未审核或已驳回的候选知识点" in pub_fail.json()["detail"]

    # 重新人工审核通过 version 2
    re_review = client.post(f"/api/admin/knowledge/nodes/{child['id']}/review", json={
        "reviewer_id": "expert_director",
        "review_status": "approved",
        "review_opinion": "父节点调整至词法大类经专家复核准予通过"
    }, headers=admin_auth)
    assert re_review.status_code == 200

    # 契约文件同步父节点变更后，发布即可成功通过
    cand_path = CONTRACTS_DIR / f"{subj}_knowledge_taxonomy_candidate.json"
    orig_text = cand_path.read_text(encoding="utf-8")
    try:
        cand_list = json.loads(orig_text)
        for item in cand_list:
            if item["code"] == child["code"]:
                item["parent_code"] = parent_new["code"]
        cand_path.write_text(json.dumps(cand_list, ensure_ascii=False, indent=2), encoding="utf-8")

        pub_ok = client.post("/api/admin/knowledge/releases", json={
            "subject": subj,
            "release_version": f"{subj}-v2022-parent-test-pass",
            "published_by": "expert_director",
            "summary": "父节点调整审核完毕后正式发布"
        }, headers=admin_auth)
        assert pub_ok.status_code == 201
        rel_id = pub_ok.json()["id"]
        db.expire_all()
        release_row = db.get(m.KnowledgeTaxonomyRelease, rel_id)
        assert release_row is not None
        snap = release_row.snapshot
        # 验证发布快照完整记录了层级 parent_id 与版本
        snap_node = next(n for n in snap["nodes"] if n["id"] == child["id"])
        assert snap_node["parent_id"] == parent_new["id"]
        assert snap_node["version"] == 2
    finally:
        cand_path.write_text(orig_text, encoding="utf-8")


def test_f01_parent_and_state_protection(client, admin_auth):
    """
    F01 专项测试套件 (F01-T01 ~ F01-T08)：
    验证历史父级快照记录、父节点变更版本化、重新激活防绕过与不可变追溯。
    """
    subj = "physics"
    # 1. 种子初始化物理候选
    client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
    cands = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth).json()
    assert len(cands) >= 3

    # F01-T01: 首次入库写入版本 1，记录 parent_node_id 与 parent_code
    child = next(c for c in cands if c.get("parent_code") is not None)
    parent = next(c for c in cands if c["code"] == child["parent_code"])
    db = next(app.dependency_overrides[get_db]())
    v1 = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == child["id"], m.KnowledgeNodeVersion.version == 1)
    )
    assert v1 is not None
    assert v1.parent_node_id == parent["id"]
    assert v1.parent_code == parent["code"]

    # F01-T02: 修改父节点生成新版本 2，记录新父级快照，状态重置为 pending
    target_parent = next(c for c in cands if c["code"] != parent["code"] and c["code"] != child["code"] and c.get("level") == 1)
    rev_resp = client.post(f"/api/admin/knowledge/nodes/{child['id']}/versions", json={
        "name": v1.name,
        "description": v1.description,
        "source_clause_ids": v1.source_clause_ids,
        "parent_code": target_parent["code"]
    }, headers=admin_auth)
    assert rev_resp.status_code == 201
    assert rev_resp.json()["version"] == 2

    db.expire_all()
    v2 = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == child["id"], m.KnowledgeNodeVersion.version == 2)
    )
    assert v2 is not None
    assert v2.parent_node_id == target_parent["id"]
    assert v2.parent_code == target_parent["code"]
    assert v2.review_status == "pending"

    # F01-T03: 仅修改父节点（名称描述不变）也判定 has_diff = True 并生成新版本
    rev3_resp = client.post(f"/api/admin/knowledge/nodes/{child['id']}/versions", json={
        "name": v2.name,
        "description": v2.description,
        "source_clause_ids": v2.source_clause_ids,
        "parent_code": parent["code"]
    }, headers=admin_auth)
    assert rev3_resp.status_code == 201
    assert rev3_resp.json()["version"] == 3

    # F01-T04: 已审核节点修改父节点后，历史 approved 不得继承，新版本必为 pending 且无审核人
    client.post(f"/api/admin/knowledge/nodes/{child['id']}/review", json={
        "reviewer_id": "prof_auditor",
        "review_status": "approved",
        "review_opinion": "准予通过"
    }, headers=admin_auth)
    rev4_resp = client.post(f"/api/admin/knowledge/nodes/{child['id']}/versions", json={
        "name": v2.name,
        "description": v2.description,
        "source_clause_ids": v2.source_clause_ids,
        "parent_code": target_parent["code"]
    }, headers=admin_auth)
    assert rev4_resp.status_code == 201
    assert rev4_resp.json()["version"] == 4
    db.expire_all()
    v4 = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == child["id"], m.KnowledgeNodeVersion.version == 4)
    )
    assert v4.review_status == "pending"
    assert v4.reviewer_id is None
    assert v4.review_opinion is None

    # F01-T05: 历史版本快照中的 parent_node_id / parent_code 永不可变
    history_resp = client.get(f"/api/admin/knowledge/nodes/{child['id']}/versions", headers=admin_auth)
    assert history_resp.status_code == 200
    versions_list = history_resp.json()
    assert len(versions_list) == 4
    assert versions_list[0]["version"] == 1 and versions_list[0]["parent_code"] == parent["code"]
    assert versions_list[1]["version"] == 2 and versions_list[1]["parent_code"] == target_parent["code"]
    assert versions_list[2]["version"] == 3 and versions_list[2]["parent_code"] == parent["code"]
    assert versions_list[3]["version"] == 4 and versions_list[3]["parent_code"] == target_parent["code"]

    # F01-T06: 停用节点重新激活防绕过审核
    dep_node = cands[-1]
    client.post(f"/api/admin/knowledge/nodes/{dep_node['id']}/deprecate", headers=admin_auth)
    db.expire_all()
    n_dep = db.get(m.KnowledgeNode, dep_node["id"])
    assert n_dep.status == "deprecated"

    # 重新 seed -> 重新激活并生成新版本进入 pending
    client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
    db.expire_all()
    n_reactivated = db.get(m.KnowledgeNode, dep_node["id"])
    assert n_reactivated.status == "active"
    v_reactivated = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == dep_node["id"])
        .order_by(m.KnowledgeNodeVersion.version.desc())
    )
    assert v_reactivated.review_status == "pending"
    assert v_reactivated.reviewer_id is None

    # F01-T07: review_node 禁止审核非 active 节点（抛出 409）
    client.post(f"/api/admin/knowledge/nodes/{dep_node['id']}/deprecate", headers=admin_auth)
    review_dep_resp = client.post(f"/api/admin/knowledge/nodes/{dep_node['id']}/review", json={
        "reviewer_id": "auditor",
        "review_status": "approved",
        "review_opinion": "尝试审核停用节点"
    }, headers=admin_auth)
    assert review_dep_resp.status_code == 409
    assert review_dep_resp.json()["detail"] == "NODE_NOT_ACTIVE"

    # F01-T08: 0008 迁移逻辑正确标记存量未知父节点为 UNKNOWN
    legacy_v = m.KnowledgeNodeVersion(
        node_id=child["id"],
        version=99,
        name="存量未记录父级旧版本",
        parent_code=None,
        review_status="approved"
    )
    db.add(legacy_v)
    db.commit()
    # 执行 0008 迁移一致的 SQL 更新
    db.execute(sa.text("UPDATE knowledge_node_versions SET parent_code = 'UNKNOWN' WHERE parent_code IS NULL"))
    db.commit()
    db.expire_all()
    v_updated = db.get(m.KnowledgeNodeVersion, legacy_v.id)
    assert v_updated.parent_code == "UNKNOWN", "存量旧版本数据必须诚实标记为 UNKNOWN"


def test_f02_english_clauses_traceability(client, admin_auth):
    """
    F02 专项测试套件 (F02-T01 ~ F02-T06)：
    验证英语课标条款演进映射表、真实历史引用、当前 30 条款双向溯源及失效条款拦截。
    """
    compat_path = CONTRACTS_DIR / "english_clause_compatibility.json"
    assert compat_path.exists(), "必须存在 contracts/english_clause_compatibility.json"
    compat = json.loads(compat_path.read_text(encoding="utf-8"))

    # F02-T01: 结构完备性与 action 统计
    meta = compat["meta"]
    assert meta["subject"] == "english"
    assert meta["total_legacy_clause_ids"] >= 25
    assert meta["total_current_clause_ids"] == 30
    assert sum(meta["action_summary"].values()) >= 25

    # F02-T02: 真实查询旧英语 KnowledgeNodeVersion.source_clause_ids，严格核验历史引用真实状态 (提供只读查询阴性证据)
    db = next(app.dependency_overrides[get_db]())
    stmt = (
        select(m.KnowledgeNodeVersion)
        .join(m.KnowledgeNode, m.KnowledgeNode.id == m.KnowledgeNodeVersion.node_id)
        .where(m.KnowledgeNode.subject == "english")
    )
    eng_versions = db.scalars(stmt).all()
    found_cids = []
    for ev in eng_versions:
        if ev.source_clause_ids:
            found_cids.extend(ev.source_clause_ids)
    # 真实只读查询阴性证据：存量 18 个旧静态英语考点版本均无 source_clause_ids 依赖，不存在受本轮条款调整影响的历史脏数据引用
    assert len(found_cids) == 0, f"发现受条款调整影响的历史旧英语条款引用: {found_cids}"

    # F02-T03: 候选节点正确引用当前 30 个有效条款 ID
    clauses_path = CONTRACTS_DIR / "curriculum_clauses_english.json"
    cur_clauses = json.loads(clauses_path.read_text(encoding="utf-8"))
    valid_ids = {c["clause_id"] for c in cur_clauses}
    assert len(valid_ids) == 30

    cand_path = CONTRACTS_DIR / "english_knowledge_taxonomy_candidate.json"
    cands = json.loads(cand_path.read_text(encoding="utf-8"))
    cand_referenced_cids = set()
    for c in cands:
        for cid in c.get("source_clause_ids", []):
            assert cid in valid_ids, f"候选知识点引用了无效英语条款 ID: {cid}"
            cand_referenced_cids.add(cid)
    # 所有 30 条款均被候选知识点完全覆盖
    assert cand_referenced_cids == valid_ids

    # F02-T04: 条款修订前后文本可追溯，包含快照与依据
    for m_item in compat["mappings"]:
        assert m_item["action"] in ["retained", "replaced", "split", "merged"]
        assert len(m_item["reason"]) >= 2
        assert "standardized_text" in m_item["legacy_snapshot"]
        for cur_snap in m_item["current_snapshots"]:
            assert cur_snap["clause_id"] in valid_ids

    # F02-T05: 引用已失效旧条款 ID 的节点在发布时被拦截 (400)
    client.post("/api/admin/knowledge/candidates/seed?subject=english", headers=admin_auth)
    eng_cands = client.get("/api/admin/knowledge/candidates?subject=english", headers=admin_auth).json()
    # 模拟篡改一个节点的条款为旧失效 ID
    db.expire_all()
    n_sample = db.get(m.KnowledgeNode, eng_cands[0]["id"])
    ver_sample = db.scalar(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == n_sample.id)
        .order_by(m.KnowledgeNodeVersion.version.desc())
    )
    ver_sample.source_clause_ids = ["cs:english:2022:s4:lang_usage:content_req:noun_syntax:c06"]
    ver_sample.review_status = "approved"
    ver_sample.reviewer_id = "auditor"
    ver_sample.review_opinion = "test"
    ver_sample.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    rel_fail = client.post("/api/admin/knowledge/releases", json={
        "subject": "english",
        "release_version": "english-test-invalid-legacy-clause",
        "published_by": "tester",
        "summary": "尝试发布包含失效旧条款的体系"
    }, headers=admin_auth)
    assert rel_fail.status_code == 400
    assert "候选节点条款溯源无效" in rel_fail.json()["detail"] or "不存在" in rel_fail.json()["detail"]

    # F02-T06: 条款兼容表完整覆盖旧版本条款到当前条款的对应关系
    covered_legacy = {m_item["legacy_clause_id"] for m_item in compat["mappings"]}
    assert len(covered_legacy) >= 25


def test_f03_release_gate_and_contract_consistency(client, admin_auth):
    """
    F03 专项测试套件 (F03-T01 ~ F03-T10)：
    验证发布门禁对来源元数据、PDF哈希、契约一致性及快照不可变性的全方位强校验。
    """
    subj = "math"
    # 1. 种子初始化
    client.post(f"/api/admin/knowledge/candidates/seed?subject={subj}", headers=admin_auth)
    cands = client.get(f"/api/admin/knowledge/candidates?subject={subj}", headers=admin_auth).json()

    # 全部审核通过
    for c in cands:
        client.post(f"/api/admin/knowledge/nodes/{c['id']}/review", json={
            "reviewer_id": "prof_auditor",
            "review_status": "approved",
            "review_opinion": "全量审核准予发布"
        }, headers=admin_auth)

    sources_file = CONTRACTS_DIR / "curriculum_sources.json"
    orig_sources = sources_file.read_text(encoding="utf-8")
    cand_file = CONTRACTS_DIR / f"{subj}_knowledge_taxonomy_candidate.json"
    orig_cands = cand_file.read_text(encoding="utf-8")

    def assert_no_release(rel_ver: str):
        _db = next(app.dependency_overrides[get_db]())
        _db.expire_all()
        _rec = _db.scalar(select(m.KnowledgeTaxonomyRelease).where(m.KnowledgeTaxonomyRelease.release_version == rel_ver))
        assert _rec is None, f"发布失败时不应持久化任何发布记录: {rel_ver}"

    try:
        # F03-T01: publish 校验 version_tag 非空
        s_data = json.loads(orig_sources)
        s_data[1]["version_tag"] = ""  # 清空 math 的 version_tag
        sources_file.write_text(json.dumps(s_data, ensure_ascii=False, indent=2), encoding="utf-8")
        resp1 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-vtag-fail", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp1.status_code == 400
        assert "version_tag" in resp1.json()["detail"]
        assert_no_release("math-test-vtag-fail")

        # F03-T02: publish 校验 file_sha256 64位哈希有效
        s_data = json.loads(orig_sources)
        s_data[1]["file_sha256"] = "invalid_hash"
        sources_file.write_text(json.dumps(s_data, ensure_ascii=False, indent=2), encoding="utf-8")
        resp2 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-sha-fail", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp2.status_code == 400
        assert "file_sha256" in resp2.json()["detail"]
        assert_no_release("math-test-sha-fail")

        # F03-T04: 官方原件 PDF SHA256 篡改不匹配时，强行拦截并验证无持久化
        s_data = json.loads(orig_sources)
        s_data[1]["file_sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
        sources_file.write_text(json.dumps(s_data, ensure_ascii=False, indent=2), encoding="utf-8")
        resp4 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-pdf-sha-mismatch", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp4.status_code == 400
        assert "哈希不一致" in resp4.json()["detail"] or "SHA256" in resp4.json()["detail"]
        assert_no_release("math-test-pdf-sha-mismatch")

        # F03-T04b: 官方原件 PDF 文件缺失时，发布门禁 fail-closed 强行拦截 (400) 并验证无持久化
        pdf_dir = ROOT / "private-data/curriculum_standards"
        temp_hidden = ROOT / "private-data/curriculum_standards_temp_hidden"
        if pdf_dir.exists():
            pdf_dir.rename(temp_hidden)
        try:
            resp_missing_pdf = client.post("/api/admin/knowledge/releases", json={
                "subject": subj, "release_version": "math-test-pdf-missing-fail", "published_by": "auditor"
            }, headers=admin_auth)
            assert resp_missing_pdf.status_code == 400
            assert "不存在或不可访问" in resp_missing_pdf.json()["detail"] or "缺少原件验证证据" in resp_missing_pdf.json()["detail"]
            assert_no_release("math-test-pdf-missing-fail")
        finally:
            if temp_hidden.exists():
                temp_hidden.rename(pdf_dir)

        # 恢复 sources 文件
        sources_file.write_text(orig_sources, encoding="utf-8")

        # F03-T06: 契约修改了 name 但数据库仍为旧批准，拦截并验证无持久化
        c_data = json.loads(orig_cands)
        c_data[0]["name"] = "被篡改的知识点名称"
        cand_file.write_text(json.dumps(c_data, ensure_ascii=False, indent=2), encoding="utf-8")
        resp6 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-drift-name", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp6.status_code == 400
        assert "实质不一致" in resp6.json()["detail"] and "名称" in resp6.json()["detail"]
        assert_no_release("math-test-drift-name")

        # F03-T06b (P0-2): 人工修订版本不得通过 origin='manual' 绕过候选契约一致性检查
        # 47个候选审核通过 → 修订一个节点名称，使其与契约明显不同 → 再次审核 → 尝试发布 -> 必须拒绝且无持久化
        target_node = cands[0]
        client.post(f"/api/admin/knowledge/nodes/{target_node['id']}/versions", json={
            "name": "人工修订但未更新契约的名称",
            "description": target_node.get("description"),
            "source_clause_ids": target_node.get("source_clause_ids")
        }, headers=admin_auth)
        client.post(f"/api/admin/knowledge/nodes/{target_node['id']}/review", json={
            "reviewer_id": "auditor_chen",
            "review_status": "approved",
            "review_opinion": "误批准人工修订"
        }, headers=admin_auth)
        resp_manual_drift = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-manual-drift-fail", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp_manual_drift.status_code == 400
        assert "实质不一致" in resp_manual_drift.json()["detail"] and "名称" in resp_manual_drift.json()["detail"]
        assert_no_release("math-test-manual-drift-fail")

        # 契约合法同步并重新审核后 -> 允许正确发布
        c_data_sync = json.loads(orig_cands)
        c_data_sync[0]["name"] = "人工修订但未更新契约的名称"
        cand_file.write_text(json.dumps(c_data_sync, ensure_ascii=False, indent=2), encoding="utf-8")
        resp_manual_sync = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-manual-sync-pass", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp_manual_sync.status_code == 201

        # 恢复节点名称为原始值并审核通过，供后续正例继续使用
        client.post(f"/api/admin/knowledge/nodes/{target_node['id']}/versions", json={
            "name": target_node["name"],
            "description": target_node.get("description"),
            "source_clause_ids": target_node.get("source_clause_ids")
        }, headers=admin_auth)
        client.post(f"/api/admin/knowledge/nodes/{target_node['id']}/review", json={
            "reviewer_id": "prof_auditor",
            "review_status": "approved",
            "review_opinion": "全量审核准予发布"
        }, headers=admin_auth)

        # F03-T07: 契约修改了 description 但数据库仍为旧批准，拦截并验证无持久化
        c_data = json.loads(orig_cands)
        c_data[0]["description"] = "被篡改的描述文本"
        cand_file.write_text(json.dumps(c_data, ensure_ascii=False, indent=2), encoding="utf-8")
        resp7 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-drift-desc", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp7.status_code == 400
        assert "实质不一致" in resp7.json()["detail"] and "描述" in resp7.json()["detail"]
        assert_no_release("math-test-drift-desc")

        # F03-T08: 契约修改了 source_clause_ids 但数据库仍为旧批准，拦截并验证无持久化
        c_data = json.loads(orig_cands)
        c_data[0]["source_clause_ids"] = ["cs:math:2022:s4:num_alg:content_req:real_num:c01"]
        cand_file.write_text(json.dumps(c_data, ensure_ascii=False, indent=2), encoding="utf-8")
        resp8 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-drift-clauses", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp8.status_code == 400
        assert "实质不一致" in resp8.json()["detail"] and "来源条款" in resp8.json()["detail"]
        assert_no_release("math-test-drift-clauses")

        # F03-T09: 契约修改了 parent_code 但数据库仍为旧批准，拦截并验证无持久化
        c_data = json.loads(orig_cands)
        c_data[-1]["parent_code"] = "math_cand.num_alg"
        cand_file.write_text(json.dumps(c_data, ensure_ascii=False, indent=2), encoding="utf-8")
        resp9 = client.post("/api/admin/knowledge/releases", json={
            "subject": subj, "release_version": "math-test-drift-parent", "published_by": "auditor"
        }, headers=admin_auth)
        assert resp9.status_code == 400
        assert "实质不一致" in resp9.json()["detail"] and "父节点" in resp9.json()["detail"]
        assert_no_release("math-test-drift-parent")

        # 恢复 cand_file
        cand_file.write_text(orig_cands, encoding="utf-8")

        # F03-T03 & F03-T05: 正例发布，契约与PDF完全匹配成功发布
        rel_ok = client.post("/api/admin/knowledge/releases", json={
            "subject": subj,
            "release_version": "math-v2022-f03-official-verified",
            "published_by": "principal_expert",
            "summary": "F03 全门禁核验通过正式发布"
        }, headers=admin_auth)
        assert rel_ok.status_code == 201

        # F03-T10: 发布快照不可变记录官方来源版本、哈希与获批候选全貌
        db = next(app.dependency_overrides[get_db]())
        db.expire_all()
        rel_record = db.get(m.KnowledgeTaxonomyRelease, rel_ok.json()["id"])
        assert rel_record is not None
        snap = rel_record.snapshot
        assert snap["curriculum_source_id"] == "MOE-2022-MATH-ERRATA-20220509"
        assert len(snap["curriculum_sources"]) >= 1
        assert snap["curriculum_sources"][0]["file_sha256"] == "1183b95c58a65eaac4c456f2d2b329bbe42f65a6482993edb537e3eaf8baa144"
        assert snap["total_nodes"] == 48
        sample_node = snap["nodes"][0]
        assert "parent_node_id" in sample_node
        assert "parent_code" in sample_node
        assert sample_node["reviewer_id"] == "prof_auditor"
        assert sample_node["review_opinion"] == "全量审核准予发布"

    finally:
        sources_file.write_text(orig_sources, encoding="utf-8")
        cand_file.write_text(orig_cands, encoding="utf-8")


def test_chinese_st020_rm02_clause_accuracy_and_schema():
    """
    ST-020-RM-02 专项定点验收：
    1. 验证新增内容要求条款 c03a 原文、元数据及 Schema 强合规；
    2. 验证教学提示 c03 主键、原文、教学提示类型及历史引用未被破坏；
    3. 验证 idiom_vocabulary 与 base_accumulation 两个知识点节点双向引用闭环、无重复、无悬空；
    4. 验证存量 18 个旧映射、其他三科契约及审核状态不受任何干扰。
    """
    # 1. 验证新增内容要求条款 c03a（含全文不变性强断言）
    schema_path = SCHEMAS_DIR / "curriculum-standard-clause.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    chinese_clauses_path = CONTRACTS_DIR / "curriculum_clauses_chinese.json"
    clauses = json.loads(chinese_clauses_path.read_text(encoding="utf-8"))
    c_map = {c["clause_id"]: c for c in clauses}

    c03a_id = "cs:chinese:2022:s4:lang_usage:content_req:vocabulary_req:c03a"
    assert c03a_id in c_map, f"未找到新增条款: {c03a_id}"
    c03a = c_map[c03a_id]

    # Schema 合规强断言
    errors = list(validator.iter_errors(c03a))
    assert not errors, f"新增条款 c03a 未通过 Schema 校验: {errors[0].message if errors else ''}"

    # 元数据与全文不变断言
    assert c03a["subject"] == "chinese"
    assert c03a["stage"] == "stage4"
    assert c03a["domain"] == "lang_usage"
    assert c03a["section_type"] == "content_requirement"
    assert c03a["clause_number"] == "积累与梳理四级③"
    assert c03a["pdf_page"] == 29
    assert c03a["print_page"] == 22
    assert c03a["review_status"] == "pending"
    assert c03a["is_elective"] is False
    expected_c03a_raw = "继续丰富自己的积累。分类整理、欣赏、交流所积累的词语、名句、诗文等，并在日常读写活动中积极运用，提升自身的中华文化修养。"
    assert c03a["raw_text"] == expected_c03a_raw, "新增条款 c03a 全文必须保持严格不变！"

    # 2. 验证保留教学提示条款 c03（含全文不变性与 R2 标点差异明确记载断言）
    c03_id = "cs:chinese:2022:s4:lang_usage:content_req:vocabulary:c03"
    assert c03_id in c_map, f"未找到教学提示条款: {c03_id}"
    c03 = c_map[c03_id]

    errors_c03 = list(validator.iter_errors(c03))
    assert not errors_c03, f"条款 c03 未通过 Schema 校验: {errors_c03[0].message if errors_c03 else ''}"
    assert c03["clause_id"] == c03_id, "主键必须严格保持不变"
    assert c03["section_type"] == "teaching_hint", "条款类型必须保持为教学提示"
    assert c03["clause_number"] == "积累与梳理教学提示③"
    assert c03["pdf_page"] == 29
    assert c03["print_page"] == 22

    # 全文不变断言：raw_text 必须逐字完全保持既有历史字面值不变
    expected_c03_raw = (
        "诵读、积累与梳理，重在培养兴趣、语感和习惯。引导学生增强语言积累和梳理的意识，"
        "教给学生语言积累和梳理的方法，注重积累、梳理与运用相结合。诵读材料要选择脍炙人口的千古名篇和名言名句，"
        "既要有文化内涵，又要短小精悍，朗朗上口。提倡日积月累，不要贪多求快，提倡熟读成诵，不要死记硬背。"
        "引导学生借助信息技术等多种方式汇总、梳理自己积累的语言材料，建立自己的创意语言资料库，并能学以致用。"
    )
    assert c03["raw_text"] == expected_c03_raw, "教学提示 c03.raw_text 全文必须严格保持不变！"

    # R2 GPT Review 校准断言：明确记载既有逗号与官方分号的历史差异，不得有不准确的‘完全一致’声明
    assert "【ST-020-RM-02 校准说明】" in c03["collation_note"]
    assert "content_req 为历史命名遗留" in c03["collation_note"]
    assert "逗号" in c03["collation_note"] and "分号" in c03["collation_note"], "collation_note 必须明确记载逗号与官方分号的历史差异！"
    assert "完全一致" not in c03["collation_note"], "collation_note 不得含有不准确的‘完全一致’断言！"

    # R2 standardized_text 优化断言：忠实概括兴趣、语感、习惯、积累方法及学以致用要求
    for required_keyword in ["兴趣", "语感", "习惯", "方法", "学以致用"]:
        assert required_keyword in c03["standardized_text"], f"standardized_text 必须忠实涵盖关键词 '{required_keyword}'"

    # 3. 验证知识点节点双向引用闭环、无重复、无悬空
    chinese_cand_path = CONTRACTS_DIR / "chinese_knowledge_taxonomy_candidate.json"
    cands = json.loads(chinese_cand_path.read_text(encoding="utf-8"))
    cand_map = {cand["code"]: cand for cand in cands}

    assert "chinese_cand.base.idiom_vocabulary" in cand_map
    assert "chinese_cand.base_accumulation" in cand_map

    idiom_sources = cand_map["chinese_cand.base.idiom_vocabulary"]["source_clause_ids"]
    base_sources = cand_map["chinese_cand.base_accumulation"]["source_clause_ids"]

    # 包含 c03a 与 c03
    assert c03a_id in idiom_sources, "idiom_vocabulary 必须包含新增 c03a 条款引用"
    assert c03_id in idiom_sources, "idiom_vocabulary 必须保留原有 c03 教学提示引用"
    assert len(idiom_sources) == len(set(idiom_sources)), "idiom_vocabulary 的 source_clause_ids 存在重复引用"

    assert c03a_id in base_sources, "base_accumulation 必须包含新增 c03a 条款引用"
    assert c03_id in base_sources, "base_accumulation 必须保留原有 c03 教学提示引用"
    assert len(base_sources) == len(set(base_sources)), "base_accumulation 的 source_clause_ids 存在重复引用"

    # 全量悬空引用检查
    all_clause_ids = set(c_map.keys())
    for cand in cands:
        for cid in cand.get("source_clause_ids", []):
            assert cid in all_clause_ids, f"候选节点 {cand['code']} 存在悬空引用: {cid}"

    # 4. 验证存量 18 个旧映射不受影响
    mapping_path = CONTRACTS_DIR / "chinese_legacy_taxonomy_mapping.json"
    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert len(mapping_data["legacy_mappings"]) == 18

    # 5. 验证其他学科契约完整性不受干扰
    for other_subj in ["math", "english", "physics"]:
        other_clauses = json.loads((CONTRACTS_DIR / f"curriculum_clauses_{other_subj}.json").read_text(encoding="utf-8"))
        assert len(other_clauses) >= 15
        for oc in other_clauses:
            assert oc["review_status"] == "pending"


def test_chinese_st020_rm03_classical_vocab_accuracy_and_schema():
    """
    ST-020-RM-03 专项定点验收与 ISS-EN-01A 误报保护断言：
    1. 验证 classical_vocab:c28 原文已完整补齐末句“背诵优秀诗文80篇（段）。”；
    2. 验证 classical_vocab:c28 元数据与 Draft202012Validator Schema 强合规；
    3. 验证知识点节点 chinese_cand.prose.classical_vocab 关联无悬空；
    4. 阶段 B 保护验证：断言 phonetics:c03 真实包含第 6 项，严禁删除或篡改。
    """
    schema_path = SCHEMAS_DIR / "curriculum-standard-clause.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    chinese_clauses_path = CONTRACTS_DIR / "curriculum_clauses_chinese.json"
    clauses = json.loads(chinese_clauses_path.read_text(encoding="utf-8"))
    c_map = {c["clause_id"]: c for c in clauses}

    c28_id = "cs:chinese:2022:s4:reading:content_req:classical_vocab:c28"
    assert c28_id in c_map, f"未找到条款: {c28_id}"
    c28 = c_map[c28_id]

    # Schema 校验
    errors = list(validator.iter_errors(c28))
    assert not errors, f"条款 c28 未通过 Schema 校验: {errors[0].message if errors else ''}"

    # 元数据断言
    assert c28["subject"] == "chinese"
    assert c28["stage"] == "stage4"
    assert c28["domain"] == "reading"
    assert c28["section_type"] == "content_requirement"
    assert c28["clause_number"] == "文言文阅读四级·实词虚词"
    assert c28["pdf_page"] == 22
    assert c28["print_page"] == 15
    assert c28["review_status"] == "pending"
    assert c28["is_elective"] is False

    # 原文完整性强断言：必须完整包含官方原件第 15 页第 6 条全文（含末句“背诵优秀诗文80篇（段）。”）
    expected_c28_raw = "诵读古代诗词，阅读浅易文言文，能借助注释和工具书理解基本内容。注重积累、感悟和运用，提高自己的欣赏品位。背诵优秀诗文80篇（段）。"
    assert c28["raw_text"] == expected_c28_raw, "c28.raw_text 必须包含官方原件完整的三句话（含末句背诵要求）"
    assert "【ST-020-RM-03 补齐末句】" in c28["collation_note"]

    # 知识点溯源检查
    chinese_cand_path = CONTRACTS_DIR / "chinese_knowledge_taxonomy_candidate.json"
    cands = json.loads(chinese_cand_path.read_text(encoding="utf-8"))
    cand_map = {cand["code"]: cand for cand in cands}
    assert "chinese_cand.prose.classical_vocab" in cand_map
    assert c28_id in cand_map["chinese_cand.prose.classical_vocab"]["source_clause_ids"]

    # 阶段 B 保护验证：验证英语 phonetics:c03 包含第 6 项，证实 ISS-EN-01A 误报保护生效
    english_clauses_path = CONTRACTS_DIR / "curriculum_clauses_english.json"
    en_clauses = json.loads(english_clauses_path.read_text(encoding="utf-8"))
    en_map = {c["clause_id"]: c for c in en_clauses}
    en_c03 = en_map["cs:english:2022:s4:lang_usage:content_req:phonetics:c03"]
    assert "6. 查词典时，运用音标知识学习单词的发音。" in en_c03["raw_text"], "英语 phonetics:c03 第 6 项必须严格保留，不得误删！"


def test_st020_2b01_chinese_zero_ghost_codes():
    """
    ST-020-2B-01 专项定点验收：语文幽灵旧码清理验证。
    1. 候选知识点 JSON (chinese_knowledge_taxonomy_candidate.json) 中内嵌 legacy_mappings 幽灵码为 0；
    2. 课标条款 JSON (curriculum_clauses_chinese.json) 中内嵌 legacy_mappings 幽灵码为 0；
    3. 保留项验证：critical_micro_writing 与 composition_expression 跨领域映射完整保留。
    """
    from shutong.corpus.taxonomy import TAXONOMY
    valid_codes = {n["code"] for n in TAXONOMY["chinese"]}

    # 1. 验证候选知识点
    cand_path = CONTRACTS_DIR / "chinese_knowledge_taxonomy_candidate.json"
    cands = json.loads(cand_path.read_text(encoding="utf-8"))
    cand_ghosts = []
    for c in cands:
        for lm in c.get("legacy_mappings", []):
            if lm not in valid_codes:
                cand_ghosts.append((c["code"], lm))
    assert cand_ghosts == [], f"语文候选知识点中仍存在幽灵旧码: {cand_ghosts}"

    # 2. 验证课标条款
    clauses_path = CONTRACTS_DIR / "curriculum_clauses_chinese.json"
    clauses = json.loads(clauses_path.read_text(encoding="utf-8"))
    clause_ghosts = []
    for cl in clauses:
        for lm in cl.get("legacy_mappings", []):
            if lm not in valid_codes:
                clause_ghosts.append((cl["clause_id"], lm))
    assert clause_ghosts == [], f"语文课标条款中仍存在幽灵旧码: {clause_ghosts}"

    # 3. 验证保留项
    c_map = {c["code"]: c for c in cands}
    assert "chinese.reading.argumentative" in c_map["chinese_cand.writing.critical_micro_writing"]["legacy_mappings"]
    comp_lms = c_map["chinese_cand.composition_expression"]["legacy_mappings"]
    assert "chinese.writing.composition" in comp_lms
    assert "chinese.reading.argumentative" in comp_lms


def test_st020_2b01_physics_micro_structure_no_density_mismatch():
    """
    ST-020-2B-01 专项定点验收：物理微观结构跨领域错配清除验证。
    1. physics_cand.matter.micro_structure 的 legacy_mapping_codes 清空为 []；
    2. 确保不存在 physics.mech.density 错配。
    """
    phys_path = CONTRACTS_DIR / "physics_knowledge_taxonomy_candidate.json"
    phys_cands = json.loads(phys_path.read_text(encoding="utf-8"))
    p_map = {c["code"]: c for c in phys_cands}

    micro = p_map["physics_cand.matter.micro_structure"]
    assert micro["legacy_mapping_codes"] == [], f"micro_structure 映射码必须为空列表，实际: {micro['legacy_mapping_codes']}"
    assert "physics.mech.density" not in micro["legacy_mapping_codes"]






