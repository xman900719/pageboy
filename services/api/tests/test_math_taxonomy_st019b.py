"""
书童 ST-019-B：数学权威知识点库自动化测试套件（V2整改增强版）

涵盖：
1. 课标条款采录完整性与 Schema 校验（全量149条官方条文、补齐代数式⑨与综合与实践(3)、9条学业要求官方原文与派生要求分离）
2. 独立官方课标结构清单与全量条文 100% 独立覆盖率核算
3. 候选知识体系与课标条文双向完备溯源（48个候选节点、pending 初始态）
4. 新旧 24 考点可审计映射与历史只读保护（81考点总盘不变、历史关联不被重写）
5. 知识库版本发布强门禁（涵盖两大核心负例：旧24节点全部approved但无新候选被拒、新候选缺少任一节点被拒、引用无效条款被拒、未审核及驳回被拒、全量批准后发布不可变快照）
6. 管理端与学生端权限强隔离（学生角色与匿名访问绝对拦截）
"""
import json
from pathlib import Path
import pytest
from sqlalchemy import select
from shutong.corpus.taxonomy import TAXONOMY
from shutong import models as m
from shutong.database import get_db
from shutong.main import app


@pytest.fixture
def db(client):
    yield from app.dependency_overrides[get_db]()


ROOT = Path(__file__).resolve().parents[3]
CLAUSES_PATH = ROOT / "contracts/curriculum_clauses_math.json"
CANDIDATE_PATH = ROOT / "contracts/math_knowledge_taxonomy_candidate.json"
MAPPING_PATH = ROOT / "contracts/math_legacy_taxonomy_mapping.json"


def test_math_curriculum_clauses_completeness_and_integrity():
    """验证150条初中数学课程标准官方条款全集的完备性与契约约束（F01整改项与ST-020-RM-01验证）。"""
    assert CLAUSES_PATH.is_file(), "Missing contracts/curriculum_clauses_math.json"
    with open(CLAUSES_PATH, "r", encoding="utf-8") as f:
        clauses = json.load(f)

    # 验证全量条款数已补齐为 150 条（ST-020-RM-01：圆章节由9条拆分为10条）
    assert len(clauses) == 150, f"Expected 150 math clauses, got {len(clauses)}"

    clause_ids = set()
    domain_counts = {"num_alg": 0, "geom": 0, "stat_prob": 0, "comp_prac": 0}

    for c in clauses:
        cid = c["clause_id"]
        assert cid not in clause_ids, f"Duplicate clause_id: {cid}"
        clause_ids.add(cid)

        assert c["subject"] == "math"
        assert c["stage"] == "stage4"
        assert c["source_id"] == "MOE-2022-MATH-ERRATA-20220509"

        domain = c["domain"]
        assert domain in domain_counts, f"Unexpected domain: {domain}"
        domain_counts[domain] += 1

        # 验证双页码偏移（初中部分偏移为 7：pdf_page = print_page + 7）
        assert c["pdf_page"] == c["print_page"] + 7, f"Page offset mismatch in {cid}: pdf={c['pdf_page']}, print={c['print_page']}"

        # 文本有效性
        assert len(c["raw_text"].strip()) > 0
        assert len(c["standardized_text"].strip()) > 0
        assert len(c["derived_requirement"].strip()) > 0
        assert c["review_status"] == "pending"

    assert domain_counts["num_alg"] == 52, f"Expected 52 num_alg clauses, got {domain_counts['num_alg']}"
    assert domain_counts["geom"] == 80, f"Expected 80 geom clauses, got {domain_counts['geom']}"
    assert domain_counts["stat_prob"] == 14, f"Expected 14 stat_prob clauses, got {domain_counts['stat_prob']}"
    assert domain_counts["comp_prac"] == 4, f"Expected 4 comp_prac clauses, got {domain_counts['comp_prac']}"

    # F01 关键断言 1：验证补齐“数与式—代数式”第⑨条“了解代数推理（例66）”
    alg_c09 = next((c for c in clauses if c["clause_id"] == "cs:math:2022-errata:s4:num_alg:content_req:alg_expr:c09"), None)
    assert alg_c09 is not None, "Missing alg_expr:c09!"
    assert alg_c09["raw_text"] == "了解代数推理（例66）。"
    assert alg_c09["print_page"] == 56
    assert alg_c09["pdf_page"] == 63

    # F01 关键断言 2：验证补齐“综合与实践”第(3)项内容要求
    comp_c03 = next((c for c in clauses if c["clause_id"] == "cs:math:2022-errata:s4:comp_prac:content_req:modeling:c03"), None)
    assert comp_c03 is not None, "Missing comp_prac:c03!"
    assert "用数学的语言，将现实问题转化为数学问题" in comp_c03["raw_text"]
    assert comp_c03["print_page"] == 78
    assert comp_c03["pdf_page"] == 85

    # F01 关键断言 3：验证 9 条学业要求的官方真实原文与派生概括严格分开
    acad_clauses = [c for c in clauses if c["section_type"] == "academic_requirement"]
    assert len(acad_clauses) == 9
    for ac in acad_clauses:
        # 官方原文必须包含官方条文标志
        assert "学业要求" in ac["raw_text"]
        assert len(ac["raw_text"]) >= 100, f"Academic requirement raw_text too short: {ac['clause_id']}"
        # 归纳概括在 derived_requirement
        assert len(ac["derived_requirement"]) > 0
        assert "官方学业要求完整原文" in ac["collation_note"]

    # 验证选学条款标识
    electives = [c for c in clauses if c["is_elective"]]
    assert len(electives) > 0, "Expected at least one elective clause"
    assert any("3var" in c["clause_id"] or "三元一次方程组" in c["raw_text"] for c in electives)


def test_independent_official_math_curriculum_clauses_audit():
    """F01要求：使用独立的官方条款清单核算覆盖率，不依赖待测 JSON 自身。"""
    with open(CLAUSES_PATH, "r", encoding="utf-8") as f:
        clauses = json.load(f)
    loaded_clause_ids = {c["clause_id"] for c in clauses}

    # 独立官方结构化条文清单定义（基于教育部2022数学课标初中第四学段目录结构）
    independent_expected_specs = [
        # 1. 数与代数: 内容要求 49 条 + 学业要求 3 条 = 52 条
        ("num_alg", "content_req:rat_num", 5),       # 有理数 ①~⑤
        ("num_alg", "content_req:real_num", 8),      # 实数 ①~⑧
        ("num_alg", "content_req:alg_expr", 9),      # 代数式 ①~⑨ (含⑨代数推理)
        ("num_alg", "content_req:quad_eq", 7),       # 方程与方程组 ①~③, ⑤~⑧
        ("num_alg", "content_req:tri_sys", 1),       # 方程与方程组 ④ 选学三元一次方程组
        ("num_alg", "content_req:ineq", 3),          # 不等式与不等式组 ①~③
        ("num_alg", "content_req:func_base", 5),     # 函数概念 ①~⑤
        ("num_alg", "content_req:lin_func", 4),      # 一次函数 ①~④
        ("num_alg", "content_req:quad_func", 4),     # 二次函数 ①~④
        ("num_alg", "content_req:inv_func", 3),      # 反比例函数 ①~③
        ("num_alg", "acad_req", 3),                  # 数与式、方程不等式、函数学业要求
        # 2. 图形与几何: 内容要求 76 条 + 学业要求 3 条 = 79 条
        ("geom", "content_req:points_lines", 7),           # 点线面角 ①~⑦
        ("geom", "content_req:intersect_parallel", 7),     # 相交平行 ①~⑦
        ("geom", "content_req:triangle", 11),              # 三角形 ①~⑪
        ("geom", "content_req:quadrilateral", 4),          # 四边形 ①~④
        ("geom", "content_req:circle", 10),                # 圆 ①~⑩ (含②垂径定理 c01b，ST-020-RM-01修复)
        ("geom", "content_req:logic", 5),                  # 定义命题定理 ①~⑤
        ("geom", "content_req:transform_axial", 4),        # 轴对称 ①~④
        ("geom", "content_req:transform_rot", 4),          # 旋转 ①~④
        ("geom", "content_req:transform_trans", 3),        # 平移 ①~③
        ("geom", "content_req:similar", 10),               # 相似与三角函数 ①~⑩
        ("geom", "content_req:projection", 4),             # 投影与三视图 ①~④
        ("geom", "content_req:coord_pos", 4),              # 位置与坐标 ①~④
        ("geom", "content_req:coord_motion", 4),           # 运动与坐标 ①~④
        ("geom", "acad_req", 3),                           # 图形性质、变化、坐标学业要求
        # 3. 统计与概率: 内容要求 12 条 + 学业要求 2 条 = 14 条
        ("stat_prob", "content_req:sampling", 10),         # 抽样与数据分析 ①~⑩
        ("stat_prob", "content_req:probability", 2),       # 随机事件概率 ①~②
        ("stat_prob", "acad_req", 2),                      # 抽样、概率学业要求
        # 4. 综合与实践: 内容要求 3 条 + 学业要求 1 条 = 4 条
        ("comp_prac", "content_req:modeling", 3),          # 项目式实践 (1)~(3)
        ("comp_prac", "acad_req:modeling", 1),             # 综合与实践学业要求
    ]

    total_expected_count = sum(count for _, _, count in independent_expected_specs)
    assert total_expected_count == 150, f"Independent expected count must be 150, got {total_expected_count}"

    # 核算每一项独立规格均在采录数据中精确匹配
    for domain, sub_tag, count in independent_expected_specs:
        matching = [cid for cid in loaded_clause_ids if domain in cid and sub_tag in cid]
        assert len(matching) == count, f"Independent audit mismatch for {domain}:{sub_tag}: expected {count}, found {len(matching)} (matches: {matching})"


def test_math_candidate_taxonomy_coverage_and_bidirectional_traceability():
    """验证48个候选知识点体系与全量150条课标条文的100%双向溯源覆盖。"""
    assert CANDIDATE_PATH.is_file(), "Missing contracts/math_knowledge_taxonomy_candidate.json"
    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    with open(CLAUSES_PATH, "r", encoding="utf-8") as f:
        clauses = json.load(f)
    all_clause_ids = {c["clause_id"] for c in clauses}
    assert len(all_clause_ids) == 150

    assert len(candidates) == 48, f"Expected 48 candidate nodes, got {len(candidates)}"

    cand_codes = set()
    covered_clause_ids = set()

    for cand in candidates:
        code = cand["code"]
        assert code.startswith("math_cand."), f"Candidate code must start with math_cand.: {code}"
        assert code not in cand_codes, f"Duplicate candidate code: {code}"
        cand_codes.add(code)

        # 严格初始状态
        assert cand["review_status"] == "pending", f"Candidate {code} must be pending!"
        assert "待" in cand["review_note"]

        # 溯源验证
        source_cids = cand.get("source_clause_ids", [])
        assert len(source_cids) > 0, f"Candidate {code} has no source clauses!"
        for cid in source_cids:
            assert cid in all_clause_ids, f"Candidate {code} references non-existent clause: {cid}"
            covered_clause_ids.add(cid)

    # 双向完备性断言：全量 149 条课标条文全部被候选知识点覆盖
    uncovered = all_clause_ids - covered_clause_ids
    assert len(uncovered) == 0, f"Uncovered clauses found: {uncovered}"


def test_legacy_math_nodes_mapping_and_historical_protection():
    """验证存量24个旧考点映射审计与历史数据保护不变项。"""
    assert MAPPING_PATH.is_file(), "Missing contracts/math_legacy_taxonomy_mapping.json"
    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        mapping_data = json.load(f)

    legacy_math = TAXONOMY["math"]
    assert len(legacy_math) == 24, "Legacy math taxonomy must remain 24 nodes"
    assert sum(len(v) for v in TAXONOMY.values()) == 81, "Total legacy taxonomy must remain 81 nodes"

    mappings = mapping_data["legacy_mappings"]
    assert len(mappings) == 24, f"Expected 24 mappings, got {len(mappings)}"

    allowed_actions = {"retained", "renamed", "split", "merged", "new", "deprecated", "pending_human_review"}
    mapped_legacy_codes = set()

    for m_rec in mappings:
        lcode = m_rec["legacy_code"]
        mapped_legacy_codes.add(lcode)
        assert m_rec["action"] in allowed_actions, f"Invalid action: {m_rec['action']}"
        assert len(m_rec["target_candidate_codes"]) > 0
        assert len(m_rec["mapping_reason"].strip()) > 0
        assert len(m_rec["compatibility_assurance"].strip()) > 0

    assert mapped_legacy_codes == {n["code"] for n in legacy_math}

    # 命名空间隔离断言：旧节点 code 与新候选 code 绝对不冲突
    legacy_codes = {n["code"] for n in legacy_math}
    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        cand_codes = {c["code"] for c in json.load(f)}
    intersection = legacy_codes.intersection(cand_codes)
    assert len(intersection) == 0, f"Legacy and candidate codes must not collide! Intersected: {intersection}"


def test_admin_knowledge_api_and_review_workflow(client, auth):
    """测试知识库管理接口：条款查询、新旧映射、初始化入库与单点专家人工审核。"""
    # 1. 查询课标条款（应为150条，含新增circle:c01b）
    res_clauses = client.get("/api/admin/knowledge/clauses?subject=math", headers=auth)
    assert res_clauses.status_code == 200
    assert len(res_clauses.json()) == 150

    # 按领域过滤
    res_num_alg = client.get("/api/admin/knowledge/clauses?subject=math&domain=num_alg", headers=auth)
    assert res_num_alg.status_code == 200
    assert len(res_num_alg.json()) == 52

    # 2. 查询新旧映射
    res_mapping = client.get("/api/admin/knowledge/legacy-mapping", headers=auth)
    assert res_mapping.status_code == 200
    map_body = res_mapping.json()
    assert map_body["summary"]["total_legacy_math_nodes"] == 24

    # 3. 初始化候选知识点入库
    res_seed = client.post("/api/admin/knowledge/candidates/seed?subject=math", headers=auth)
    assert res_seed.status_code == 201
    assert res_seed.json()["total_nodes"] >= 48

    # 4. 获取入库候选列表
    res_cands = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth)
    assert res_cands.status_code == 200
    cand_nodes = res_cands.json()
    assert len(cand_nodes) >= 48
    sample_node = cand_nodes[0]
    assert sample_node["review_status"] == "pending"

    # 5. 人工审核操作
    node_id = sample_node["id"]
    # 驳回测试
    res_reject = client.post(
        f"/api/admin/knowledge/nodes/{node_id}/review",
        json={
            "reviewer_id": "expert_teacher_01",
            "review_status": "rejected",
            "review_opinion": "知识点描述与课标原文有出入，退回修改。"
        },
        headers=auth
    )
    assert res_reject.status_code == 200
    assert res_reject.json()["review_status"] == "rejected"
    assert res_reject.json()["reviewer_id"] == "expert_teacher_01"

    # 批准测试
    res_approve = client.post(
        f"/api/admin/knowledge/nodes/{node_id}/review",
        json={
            "reviewer_id": "expert_teacher_01",
            "review_status": "approved",
            "review_opinion": "已按要求复核，符合2022课标初中要求，予以通过。"
        },
        headers=auth
    )
    assert res_approve.status_code == 200
    assert res_approve.json()["review_status"] == "approved"


def test_candidate_nodes_query_scenarios(client, auth):
    """
    测试候选知识点查询接口的契约权威性与解耦隔离（F01/B01 核心契约验证）：
    覆盖 6 大场景：
    1. 空数据库：精确返回 48 个待初始化候选节点（is_seeded=False, review_status=pending）。
    2. 仅存量旧 24 个考点：依然精确返回 48 个新候选节点，无任何旧考点混入，全部 is_seeded=False。
    3. 部分新候选入库（例如仅创建前 5 个）：完整返回 48 个节点，已入库的 is_seeded=True，未入库的 is_seeded=False。
    4. 数据库中真实审核状态（approved, pending, rejected）共存：真实反映在接口输出中，不被契约默认值静默覆盖。
    5. 数据库中存在额外的 math_cand.* 异常节点：不污染候选展示列表，候选集合恒定为 48 个契约定义节点。
    6. 旧 24 个考点与新 48 个候选全量共存：只返回 48 个新候选，旧考点严格隔离。
    """
    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        contract_cands = json.load(f)
    assert len(contract_cands) == 48
    contract_codes = [c["code"] for c in contract_cands]

    # 场景 1：空数据库
    res_empty = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth)
    assert res_empty.status_code == 200
    cands_empty = res_empty.json()
    assert len(cands_empty) == 48
    for item in cands_empty:
        assert item["code"].startswith("math_cand.")
        assert item["id"] is None
        assert item["is_seeded"] is False
        assert item["review_status"] == "pending"
        assert item["version"] == 1

    # 场景 2：仅存量旧 24 个考点
    for leg in TAXONOMY["math"]:
        client.post(
            "/api/admin/knowledge/nodes",
            json={"subject": "math", "code": leg["code"], "name": leg["name"]},
            headers=auth
        )
    res_leg = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth)
    assert res_leg.status_code == 200
    cands_leg = res_leg.json()
    assert len(cands_leg) == 48
    for item in cands_leg:
        assert item["code"].startswith("math_cand.")
        assert not item["code"].startswith("math.num_alg.")
        assert not item["code"].startswith("math.func.")
        assert item["is_seeded"] is False
        assert item["id"] is None

    # 场景 3：部分新候选入库（仅录入前 5 个节点）
    seeded_5_codes = set()
    node_ids = []
    for c in sorted(contract_cands[:5], key=lambda x: x.get("level", 3)):
        c_resp = client.post(
            "/api/admin/knowledge/nodes",
            json={
                "subject": "math",
                "code": c["code"],
                "name": c["name"],
                "description": c.get("description"),
                "source_clause_ids": c.get("source_clause_ids")
            },
            headers=auth
        )
        assert c_resp.status_code == 201
        seeded_5_codes.add(c["code"])
        node_ids.append(c_resp.json()["id"])

    res_partial = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth)
    assert res_partial.status_code == 200
    cands_partial = res_partial.json()
    assert len(cands_partial) == 48
    for item in cands_partial:
        if item["code"] in seeded_5_codes:
            assert item["is_seeded"] is True
            assert item["id"] is not None
        else:
            assert item["is_seeded"] is False
            assert item["id"] is None

    # 场景 4：数据库中真实审核状态（approved, pending, rejected）并存
    client.post(
        f"/api/admin/knowledge/nodes/{node_ids[0]}/review",
        json={"reviewer_id": "math_expert_alice", "review_status": "approved", "review_opinion": "已复核通过"},
        headers=auth
    )
    client.post(
        f"/api/admin/knowledge/nodes/{node_ids[1]}/review",
        json={"reviewer_id": "math_expert_bob", "review_status": "rejected", "review_opinion": "描述需订正"},
        headers=auth
    )

    res_mixed = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth)
    assert res_mixed.status_code == 200
    mixed_map = {item["code"]: item for item in res_mixed.json()}
    node0_code = contract_cands[0]["code"]
    node1_code = contract_cands[1]["code"]
    node2_code = contract_cands[2]["code"]
    assert mixed_map[node0_code]["review_status"] == "approved"
    assert mixed_map[node0_code]["reviewer_id"] == "math_expert_alice"
    assert mixed_map[node0_code]["review_opinion"] == "已复核通过"
    assert mixed_map[node1_code]["review_status"] == "rejected"
    assert mixed_map[node1_code]["reviewer_id"] == "math_expert_bob"
    assert mixed_map[node2_code]["review_status"] == "pending"

    # 场景 5：数据库中存在额外的 math_cand.* 异常节点（契约外非法节点，不污染候选列表）
    rogue_resp = client.post(
        "/api/admin/knowledge/nodes",
        json={
            "subject": "math",
            "code": "math_cand.extra.unapproved_rogue",
            "name": "非法额外候选考点",
            "description": "契约外节点，不应污染候选清单"
        },
        headers=auth
    )
    assert rogue_resp.status_code == 201

    res_rogue = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth)
    assert res_rogue.status_code == 200
    cands_rogue = res_rogue.json()
    assert len(cands_rogue) == 48, f"Expected 48 candidate nodes, got {len(cands_rogue)}"
    rogue_codes = [c["code"] for c in cands_rogue]
    assert rogue_codes == contract_codes
    assert "math_cand.extra.unapproved_rogue" not in rogue_codes

    # 场景 6：旧 24 考点与新 48 候选全量共存
    res_seed = client.post("/api/admin/knowledge/candidates/seed?subject=math", headers=auth)
    assert res_seed.status_code == 201
    res_all = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth)
    assert res_all.status_code == 200
    cands_all = res_all.json()
    assert len(cands_all) == 48
    for item in cands_all:
        assert item["code"].startswith("math_cand.")
        assert item["is_seeded"] is True
        assert item["id"] is not None


def test_release_gate_enforcement_and_negative_cases(client, auth, db):
    """
    测试正式版本发布的强门禁机制（F02整改项强化验证）：
    涵盖完整负例防御断言与全流程门禁：
    - R01：仅旧 24 节点全部 approved，48 个新候选均不存在时，必须拒绝发布。
    - R02：新候选缺少任一节点（如 47/48 approved），必须拒绝发布。
    - R03：48 个候选全获批，但数据库多出 1 个额外活跃候选节点，必须拒绝发布。
    - R04：存在 pending 或 rejected 候选节点，必须拒绝发布。
    - R05：候选节点来源条款为空列表，必须拒绝发布。
    - R06：候选节点引用不存在的官方课标条款，必须拒绝发布。
    - R07：缺乏必要审核人或审核意见，必须拒绝发布。
    - R08：节点实质内容更新产生新版本后未审核，必须拒绝发布。
    - R09：全量 48 个候选 approved 且证据完备时，发布不可变快照成功。
    - R10：重复发布同一版本，必须返回 409 拒绝。
    """
    # =========================================================================
    # 负例 1：仅存量旧 24 个节点 approved，47 个新候选完全不存在 -> 必须拒绝发布
    # =========================================================================
    # 模拟在数据库中只创建了旧 math.* 节点并设为 approved
    for leg in TAXONOMY["math"]:
        n_resp = client.post(
            "/api/admin/knowledge/nodes",
            json={"subject": "math", "code": leg["code"], "name": leg["name"]},
            headers=auth
        )
        if n_resp.status_code == 201:
            nid = n_resp.json()["id"]
            client.post(
                f"/api/admin/knowledge/nodes/{nid}/review",
                json={"reviewer_id": "auditor", "review_status": "approved", "review_opinion": "旧节点审核"},
                headers=auth
            )

    # 此时尝试发布新版数学知识库 -> 必须返回 400 拦截！
    res_neg1 = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg1",
            "published_by": "admin_owner",
            "summary": "尝试仅凭旧节点发布新版"
        },
        headers=auth
    )
    assert res_neg1.status_code == 400
    assert "未检测到任何 math 新候选知识点" in res_neg1.json()["detail"]
    assert "历史兼容考点不能独立满足新版发布条件" in res_neg1.json()["detail"]

    # =========================================================================
    # 负例 2：新候选缺少任一节点（例如仅创建了前 47 个节点且全通过，缺少第 48 个）-> 必须拒绝发布
    # =========================================================================
    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)
    assert len(candidates) == 48

    # 手动录入前 47 个节点并审核通过（故意跳过最后一个候选节点）
    cands_sub = candidates[:-1]
    last_cand = candidates[-1]

    created_ids = []
    for c in sorted(cands_sub, key=lambda x: x.get("level", 3)):
        c_resp = client.post(
            "/api/admin/knowledge/nodes",
            json={
                "subject": "math",
                "code": c["code"],
                "name": c["name"],
                "description": c.get("description"),
                "parent_code": c.get("parent_code"),
                "source_clause_ids": c.get("source_clause_ids")
            },
            headers=auth
        )
        if c_resp.status_code == 201:
            nid = c_resp.json()["id"]
            created_ids.append(nid)
            # 设为 approved
            client.post(
                f"/api/admin/knowledge/nodes/{nid}/review",
                json={
                    "reviewer_id": "math_expert",
                    "review_status": "approved",
                    "review_opinion": "审核通过"
                },
                headers=auth
            )

    # 此时 47 个节点均已 approved，但缺少第 48 个节点 -> 尝试发布必须返回 400！
    res_neg2 = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg2",
            "published_by": "admin_owner",
            "summary": "尝试在缺失1个节点时发布"
        },
        headers=auth
    )
    assert res_neg2.status_code == 400
    assert "候选知识体系节点不完整" in res_neg2.json()["detail"]
    assert "缺少 1 个必要候选节点" in res_neg2.json()["detail"]
    assert last_cand["code"] in res_neg2.json()["detail"]

    # =========================================================================
    # 补齐第 48 个节点，但测试其他异常状态拦截
    # =========================================================================
    c_last_resp = client.post(
        "/api/admin/knowledge/nodes",
        json={
            "subject": "math",
            "code": last_cand["code"],
            "name": last_cand["name"],
            "description": last_cand.get("description"),
            "parent_code": last_cand.get("parent_code"),
            "source_clause_ids": last_cand.get("source_clause_ids")
        },
        headers=auth
    )
    assert c_last_resp.status_code == 201
    nid_last = c_last_resp.json()["id"]

    # 负例 4A：第 48 个节点为 pending 状态 -> 尝试发布必须返回 400！
    res_neg4a = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg4a",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_neg4a.status_code == 400
    assert "未通过" in res_neg4a.json()["detail"]

    # 负例 4B：第 48 个节点为 rejected 状态 -> 尝试发布必须返回 400！
    client.post(
        f"/api/admin/knowledge/nodes/{nid_last}/review",
        json={
            "reviewer_id": "math_auditor",
            "review_status": "rejected",
            "review_opinion": "考点粒度不符，予以退回。"
        },
        headers=auth
    )
    res_neg4b = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg4b",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_neg4b.status_code == 400
    assert "未通过" in res_neg4b.json()["detail"]

    # =========================================================================
    # 负例 3：全量 48 个候选已 approved，但数据库多出 1 个额外活跃候选节点 -> 必须拒绝发布
    # =========================================================================
    # 先批准第 48 个节点
    client.post(
        f"/api/admin/knowledge/nodes/{nid_last}/review",
        json={
            "reviewer_id": "math_panel_chair",
            "review_status": "approved",
            "review_opinion": "经专家组闭门复核，符合2022课标要求，全量通过。"
        },
        headers=auth
    )

    # 插入一个契约外的额外活跃候选节点
    rogue_resp = client.post(
        "/api/admin/knowledge/nodes",
        json={
            "subject": "math",
            "code": "math_cand.extra.unapproved_rogue",
            "name": "非法额外候选考点",
            "description": "契约外的额外节点",
            "source_clause_ids": last_cand.get("source_clause_ids")
        },
        headers=auth
    )
    assert rogue_resp.status_code == 201
    rogue_id = rogue_resp.json()["id"]
    client.post(
        f"/api/admin/knowledge/nodes/{rogue_id}/review",
        json={"reviewer_id": "math_auditor", "review_status": "approved", "review_opinion": "误批准额外节点"},
        headers=auth
    )

    res_neg_extra = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg_extra",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_neg_extra.status_code == 400
    assert "额外活跃候选节点" in res_neg_extra.json()["detail"] or "extra_codes" in res_neg_extra.json()["detail"]

    # 将额外节点标记为废弃（非 active），使其退出候选集合
    client.post(f"/api/admin/knowledge/nodes/{rogue_id}/deprecate", headers=auth)

    # =========================================================================
    # 负例 5：候选节点来源条款为空列表 -> 必须拒绝发布 (F02/B03)
    # =========================================================================
    ver_last = db.scalars(
        select(m.KnowledgeNodeVersion)
        .where(m.KnowledgeNodeVersion.node_id == nid_last)
        .order_by(m.KnowledgeNodeVersion.version.desc())
    ).first()
    orig_cids = list(ver_last.source_clause_ids or [])
    ver_last.source_clause_ids = []
    db.commit()

    res_neg_empty_source = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg_empty_source",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_neg_empty_source.status_code == 400
    assert "缺失来源条款" in res_neg_empty_source.json()["detail"] or "没有任何来源条款依据" in res_neg_empty_source.json()["detail"]

    # =========================================================================
    # 负例 6：候选节点引用不存在的官方课标条款 -> 必须拒绝发布
    # =========================================================================
    ver_last.source_clause_ids = ["cs:math:2022-errata:fake_clause_nonexistent_999"]
    db.commit()

    res_neg_invalid_clause = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg_invalid_clause",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_neg_invalid_clause.status_code == 400
    assert "引用了不存在的官方课标条款" in res_neg_invalid_clause.json()["detail"] or "条款溯源无效" in res_neg_invalid_clause.json()["detail"]

    # =========================================================================
    # 负例 7：候选节点审核证据不完整（如 reviewer_id 纯空格）-> 必须拒绝发布
    # =========================================================================
    ver_last.source_clause_ids = orig_cids
    ver_last.reviewer_id = "   "
    db.commit()

    res_neg_missing_evidence = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg_missing_evidence",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_neg_missing_evidence.status_code == 400
    assert "缺乏完整的人工审核证据" in res_neg_missing_evidence.json()["detail"] or "审核证据不完整" in res_neg_missing_evidence.json()["detail"]

    # 恢复合法审核证据
    ver_last.reviewer_id = "math_panel_chair"
    db.commit()

    # =========================================================================
    # 负例 8：节点实质内容更新产生新版本后未审核（新版本默认为 pending）-> 必须拒绝发布
    # =========================================================================
    first_nid = created_ids[0]
    rev_resp = client.post(
        f"/api/admin/knowledge/nodes/{first_nid}/versions",
        json={"name": "数与代数（实质更新）", "description": "更新考点描述"},
        headers=auth
    )
    assert rev_resp.status_code == 201

    res_neg_new_ver = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg_new_ver",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_neg_new_ver.status_code == 400
    assert "未通过" in res_neg_new_ver.json()["detail"] or "未审核" in res_neg_new_ver.json()["detail"]

    # 审核批准新版本（F01：已自动继承上一版本合法来源条款）
    client.post(
        f"/api/admin/knowledge/nodes/{first_nid}/review",
        json={
            "reviewer_id": "math_panel_chair",
            "review_status": "approved",
            "review_opinion": "修订版本经专家组复核，符合2022课标要求，予以通过。"
        },
        headers=auth
    )

    # =========================================================================
    # 负例 8b (P0-2)：人工修订导致节点名称与磁盘候选契约实质不符 -> 必须坚决拒绝发布 (400)
    # 48个候选审核通过 → 修订一个节点名称，使其与契约明显不同 → 再次审核 → 尝试发布 -> 预期必须拒绝
    # =========================================================================
    res_drift_blocked = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.neg_drift_blocked",
            "published_by": "admin_owner",
            "summary": "尝试发布与契约不符的人工修订旧批准"
        },
        headers=auth
    )
    assert res_drift_blocked.status_code == 400
    assert "实质不一致" in res_drift_blocked.json()["detail"] and "名称" in res_drift_blocked.json()["detail"]

    # =========================================================================
    # 正例：将权威候选契约合法同步并重新审核后 -> 正式发布成功
    # =========================================================================
    cand_path = Path(CANDIDATE_PATH)
    orig_cands = cand_path.read_text(encoding="utf-8")
    try:
        c_list = json.loads(orig_cands)
        for item in c_list:
            if item["code"] == "math_cand.num_alg":
                item["name"] = "数与代数（实质更新）"
                item["description"] = "更新考点描述"
        cand_path.write_text(json.dumps(c_list, ensure_ascii=False, indent=2), encoding="utf-8")

        res_release_ok = client.post(
            "/api/admin/knowledge/releases",
            json={
                "subject": "math",
                "release_version": "v2022.1.0-official-signed",
                "published_by": "admin_owner",
                "summary": "全量48个候选考点通过学科专家审核后的正式版本"
            },
            headers=auth
        )
        assert res_release_ok.status_code == 201
        release_info = res_release_ok.json()
        assert release_info["release_version"] == "v2022.1.0-official-signed"
        assert release_info["status"] == "published"
        assert release_info["total_nodes"] == 48
        assert release_info["curriculum_source_id"] == "MOE-2022-MATH-ERRATA-20220509"
    finally:
        cand_path.write_text(orig_cands, encoding="utf-8")

    # 快照内容不可变性与纯净性验证
    rel_db = db.scalar(select(m.KnowledgeTaxonomyRelease).where(m.KnowledgeTaxonomyRelease.release_version == "v2022.1.0-official-signed"))
    assert rel_db is not None
    snapshot_nodes = rel_db.snapshot["nodes"]
    assert len(snapshot_nodes) == 48
    for sn in snapshot_nodes:
        assert sn["code"].startswith("math_cand.")
        assert not sn["code"].startswith("math.num_alg.")
        assert not sn["code"].startswith("math.func.")
        assert sn["code"] != "math_cand.extra.unapproved_rogue"
        assert sn["reviewer_id"] is not None
        assert len(sn["source_clause_ids"]) >= 1

    # 防重发布（409 冲突）
    res_dup = client.post(
        "/api/admin/knowledge/releases",
        json={
            "subject": "math",
            "release_version": "v2022.1.0-official-signed",
            "published_by": "admin_owner"
        },
        headers=auth
    )
    assert res_dup.status_code == 409

    # 查询发布记录
    res_releases = client.get("/api/admin/knowledge/releases?subject=math", headers=auth)
    assert res_releases.status_code == 200
    assert any(r["release_version"] == "v2022.1.0-official-signed" for r in res_releases.json())


def test_node_version_revision_and_source_clauses_api_integration(client, auth):
    """
    F01 真实 API 集成测试：版本修订与来源条款关联业务闭环。
    验证要求：
    1. 候选考点全量入库并经专家审核通过；
    2. 创建新版本时，若未显式传 source_clause_ids，自动继承上一版本的来源条款；
    3. 新版本状态强制为 pending，审核人和意见置空；
    4. 此时尝试发布被门禁以 HTTP 400 拦截；
    5. 创建新版本并显式传入空来源条款 []，审核通过后尝试发布被门禁以 HTTP 400 拦截（缺失来源条款）；
    6. 创建新版本并显式传入合法条款或默认继承，经真实 API 审核通过后，正式发布成功；
    7. 全流程纯 API 交互，绝不直接修改 ORM 或 SQL。
    """
    # 1. 种子初始化入库
    res_seed = client.post("/api/admin/knowledge/candidates/seed?subject=math", headers=auth)
    assert res_seed.status_code == 201

    cands = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth).json()
    assert len(cands) == 48

    # 2. 全量批准 48 个节点的第一版本
    for c in cands:
        client.post(
            f"/api/admin/knowledge/nodes/{c['id']}/review",
            json={
                "reviewer_id": "auditor_v1",
                "review_status": "approved",
                "review_opinion": "初版审核通过"
            },
            headers=auth
        )

    target_node = cands[0]
    target_nid = target_node["id"]
    orig_sources = target_node["source_clause_ids"]
    assert len(orig_sources) >= 1

    # 3. 测试继承：创建版本 2，不传 source_clause_ids
    rev_resp1 = client.post(
        f"/api/admin/knowledge/nodes/{target_nid}/versions",
        json={"name": "数与代数（第一轮修订）", "description": "继承上一版本来源条款"},
        headers=auth
    )
    assert rev_resp1.status_code == 201
    assert rev_resp1.json()["version"] == 2

    # 查询验证版本 2 继承了来源条款，且处于 pending，审核人为空
    cands_after_v2 = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth).json()
    v2_info = next(c for c in cands_after_v2 if c["id"] == target_nid)
    assert v2_info["version"] == 2
    assert v2_info["name"] == "数与代数（第一轮修订）"
    assert v2_info["review_status"] == "pending"
    assert v2_info["reviewer_id"] is None
    assert v2_info["source_clause_ids"] == orig_sources

    # 此时尝试发布正式版本 -> 必须被拦截（400，存在未审核节点）
    res_pub_blocked = client.post(
        "/api/admin/knowledge/releases",
        json={"subject": "math", "release_version": "v_f01_test_pending", "published_by": "owner"},
        headers=auth
    )
    assert res_pub_blocked.status_code == 400
    assert "未通过" in res_pub_blocked.json()["detail"] or "未审核" in res_pub_blocked.json()["detail"]

    # 4. 测试显式传入空来源条款 []：创建版本 3
    rev_resp2 = client.post(
        f"/api/admin/knowledge/nodes/{target_nid}/versions",
        json={"name": "数与代数（空来源测试）", "description": "故意传入空来源列表", "source_clause_ids": []},
        headers=auth
    )
    assert rev_resp2.status_code == 201
    assert rev_resp2.json()["version"] == 3

    # 对版本 3 审核通过
    client.post(
        f"/api/admin/knowledge/nodes/{target_nid}/review",
        json={"reviewer_id": "auditor_careless", "review_status": "approved", "review_opinion": "误批准空来源"},
        headers=auth
    )

    # 尝试发布 -> 必须被门禁拦截（400，没有任何来源条款依据）
    res_pub_empty_source = client.post(
        "/api/admin/knowledge/releases",
        json={"subject": "math", "release_version": "v_f01_test_empty_source", "published_by": "owner"},
        headers=auth
    )
    assert res_pub_empty_source.status_code == 400
    assert "缺失来源条款" in res_pub_empty_source.json()["detail"] or "没有任何来源条款依据" in res_pub_empty_source.json()["detail"]

    # 5. 显式提供合法来源条款或恢复继承：创建版本 4
    rev_resp3 = client.post(
        f"/api/admin/knowledge/nodes/{target_nid}/versions",
        json={"name": "数与代数（最终修订版）", "description": "显式提供合法来源条款", "source_clause_ids": orig_sources},
        headers=auth
    )
    assert rev_resp3.status_code == 201
    assert rev_resp3.json()["version"] == 4

    # 对版本 4 进行正规审核批准
    client.post(
        f"/api/admin/knowledge/nodes/{target_nid}/review",
        json={"reviewer_id": "math_senior_expert", "review_status": "approved", "review_opinion": "修订版本经专家组复核，予以通过"},
        headers=auth
    )

    # 负例：契约未同步时，尝试发布人工修订版本 -> 坚决被拦截 (400)
    res_pub_drift = client.post(
        "/api/admin/knowledge/releases",
        json={"subject": "math", "release_version": "v_f01_test_drift_fail", "published_by": "owner"},
        headers=auth
    )
    assert res_pub_drift.status_code == 400
    assert "实质不一致" in res_pub_drift.json()["detail"] and "名称" in res_pub_drift.json()["detail"]

    # 正例：将契约合法同步并重新发布 -> 正式发布成功！
    cand_path = Path(CANDIDATE_PATH)
    orig_cands = cand_path.read_text(encoding="utf-8")
    try:
        c_list = json.loads(orig_cands)
        for item in c_list:
            if item["code"] == "math_cand.num_alg":
                item["name"] = "数与代数（最终修订版）"
                item["description"] = "显式提供合法来源条款"
        cand_path.write_text(json.dumps(c_list, ensure_ascii=False, indent=2), encoding="utf-8")

        res_pub_ok = client.post(
            "/api/admin/knowledge/releases",
            json={"subject": "math", "release_version": "v_f01_test_final_ok", "published_by": "owner", "summary": "版本修订后重新审核通过"},
            headers=auth
        )
        assert res_pub_ok.status_code == 201
        release_data = res_pub_ok.json()
        assert release_data["status"] == "published"
        assert release_data["total_nodes"] == 48
    finally:
        cand_path.write_text(orig_cands, encoding="utf-8")


def test_candidate_seed_contract_diff_and_sync_workflow(client, auth):
    """
    F02 契约更新与已有数据库候选同步/修订隔离测试：
    1. 导入初始契约候选，全量审核通过；
    2. 再次执行 seed 保持幂等，不生成重复版本；
    3. 契约更新后（模拟某候选名称与描述更新），调用 seed 接口触发授权同步；
    4. 系统检测到差异，为变动候选创建新版本 (version+1)，状态自动重置为 pending；
    5. 管理查询接口如实显示最新版本内容和 pending 状态；
    6. 未审核前发布被门禁拦截；
    7. 对新版本重新审核批准后，正式发布成功；
    8. 存量考点与历史数据不受破坏。
    """
    # 1. 导入初始契约候选
    res_seed1 = client.post("/api/admin/knowledge/candidates/seed?subject=math", headers=auth)
    assert res_seed1.status_code == 201
    assert res_seed1.json()["seeded_count"] == 48
    assert res_seed1.json()["revised_count"] == 0

    # 2. 幂等性校验：在契约未变动时重复调用 seed，不创建重复版本
    res_seed_idem = client.post("/api/admin/knowledge/candidates/seed?subject=math", headers=auth)
    assert res_seed_idem.status_code == 201
    assert res_seed_idem.json()["seeded_count"] == 0
    assert res_seed_idem.json()["revised_count"] == 0

    # 3. 全量批准 48 个候选
    cands = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth).json()
    for c in cands:
        client.post(
            f"/api/admin/knowledge/nodes/{c['id']}/review",
            json={"reviewer_id": "math_auditor_init", "review_status": "approved", "review_opinion": "初版合格"},
            headers=auth
        )

    # 4. 模拟契约文件局部更新（在 try...finally 中确保文件绝对恢复）
    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        orig_content = f.read()

    try:
        cand_list = json.loads(orig_content)
        # 修改第 1 个候选考点的名称和描述
        cand_list[0]["name"] = "有理数及其运算（2026年修订版）"
        cand_list[0]["description"] = "更新后的考点描述，增加教学建议"
        with open(CANDIDATE_PATH, "w", encoding="utf-8") as f:
            json.dump(cand_list, f, ensure_ascii=False, indent=2)

        # 5. 执行授权同步
        res_sync = client.post("/api/admin/knowledge/candidates/seed?subject=math", headers=auth)
        assert res_sync.status_code == 201
        assert res_sync.json()["seeded_count"] == 0
        assert res_sync.json()["revised_count"] == 1  # 精确识别差异并修订 1 个节点！

        # 6. 管理查询显示最新版本与 pending 状态
        cands_updated = client.get("/api/admin/knowledge/candidates?subject=math", headers=auth).json()
        assert len(cands_updated) == 48
        revised_node = next(c for c in cands_updated if c["code"] == cand_list[0]["code"])
        assert revised_node["version"] == 2
        assert revised_node["name"] == "有理数及其运算（2026年修订版）"
        assert revised_node["description"] == "更新后的考点描述，增加教学建议"
        assert revised_node["review_status"] == "pending"
        assert revised_node["reviewer_id"] is None

        # 其他未变动的节点依然保持 version=1 与 approved
        other_nodes = [c for c in cands_updated if c["code"] != cand_list[0]["code"]]
        assert all(c["version"] == 1 and c["review_status"] == "approved" for c in other_nodes)

        # 7. 此时发布必须被拒绝（未审核）
        res_release_blocked = client.post(
            "/api/admin/knowledge/releases",
            json={"subject": "math", "release_version": "v2026.f02.sync", "published_by": "owner"},
            headers=auth
        )
        assert res_release_blocked.status_code == 400
        assert "未通过" in res_release_blocked.json()["detail"] or "未审核" in res_release_blocked.json()["detail"]

        # 8. 重新审核批准修订后的版本 2
        client.post(
            f"/api/admin/knowledge/nodes/{revised_node['id']}/review",
            json={
                "reviewer_id": "math_senior_chair",
                "review_status": "approved",
                "review_opinion": "契约同步修订版本复核通过"
            },
            headers=auth
        )

        # 9. 审核通过后，发布正式版本成功！
        res_release_ok = client.post(
            "/api/admin/knowledge/releases",
            json={"subject": "math", "release_version": "v2026.f02.sync", "published_by": "owner"},
            headers=auth
        )
        assert res_release_ok.status_code == 201
        assert res_release_ok.json()["total_nodes"] == 48
    finally:
        # 严格恢复原始契约文件
        with open(CANDIDATE_PATH, "w", encoding="utf-8") as f:
            f.write(orig_content)


def test_student_and_anonymous_endpoint_isolation(client):
    """测试学生端与匿名访问安全隔离：绝对禁止接触知识点审核与管理接口。"""
    # 匿名访问拦截 (401)
    assert client.get("/api/admin/knowledge/clauses").status_code == 401
    assert client.get("/api/admin/knowledge/candidates").status_code == 401
    assert client.get("/api/admin/knowledge/legacy-mapping").status_code == 401
    assert client.post("/api/admin/knowledge/candidates/seed").status_code == 401
    assert client.post("/api/admin/knowledge/releases", json={"subject": "math", "release_version": "v1"}).status_code == 401

    # 模拟学生身份令牌访问（非 admin）拦截
    student_auth = {"Authorization": "Bearer student_token_demo"}
    assert client.get("/api/admin/knowledge/clauses", headers=student_auth).status_code in [401, 403]
    assert client.post("/api/admin/knowledge/candidates/seed", headers=student_auth).status_code in [401, 403]
    assert client.post("/api/admin/knowledge/releases", json={"subject": "math"}, headers=student_auth).status_code in [401, 403]


def test_curriculum_clauses_semantic_mapping_precision():
    """
    针对专业内容评审意见的语义定点回归测试：
    验证三角形、四边形、抽样、圆、代数式、方程及旧考点映射的精确性与负例防御。
    """
    with open(CLAUSES_PATH, "r", encoding="utf-8") as f:
        clauses = json.load(f)
    c_map = {c["clause_id"]: c for c in clauses}

    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)
    cand_map = {c["code"]: c for c in candidates}

    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        mapping_data = json.load(f)
    mappings = {m["legacy_code"]: m for m in mapping_data["legacy_mappings"]}

    # 1. 验证代数式 c08 与 c09 无重复拼接
    c08 = c_map["cs:math:2022-errata:s4:num_alg:content_req:alg_expr:c08"]
    c09 = c_map["cs:math:2022-errata:s4:num_alg:content_req:alg_expr:c09"]
    assert "了解代数推理（例66）" not in c08["raw_text"], "c08 must not contain algebra reasoning text!"
    assert "分式和最简分式" in c08["raw_text"]
    assert c09["raw_text"] == "了解代数推理（例66）。"

    # 2. 验证三角形条款精确定向
    tri_c03 = "cs:math:2022-errata:s4:geom:content_req:triangle:c03"
    tri_c04 = "cs:math:2022-errata:s4:geom:content_req:triangle:c04"
    tri_c05 = "cs:math:2022-errata:s4:geom:content_req:triangle:c05"
    tri_c06 = "cs:math:2022-errata:s4:geom:content_req:triangle:c06"
    tri_c07 = "cs:math:2022-errata:s4:geom:content_req:triangle:c07"
    tri_c08 = "cs:math:2022-errata:s4:geom:content_req:triangle:c08"
    tri_c09 = "cs:math:2022-errata:s4:geom:content_req:triangle:c09"
    tri_c10 = "cs:math:2022-errata:s4:geom:content_req:triangle:c10"
    tri_c11 = "cs:math:2022-errata:s4:geom:content_req:triangle:c11"
    quad_c04 = "cs:math:2022-errata:s4:geom:content_req:quadrilateral:c04"

    # 全等三角形：包含 c03, c04, c05, c10, c11；绝不能包含等腰(c08)和直角勾股(c09)
    congruent = cand_map["math_cand.geo.congruent_triangles"]["source_clause_ids"]
    assert tri_c03 in congruent and tri_c04 in congruent and tri_c05 in congruent
    assert tri_c10 in congruent and tri_c11 in congruent
    assert tri_c08 not in congruent, "Congruent triangles must NOT contain isosceles clause c08!"
    assert tri_c09 not in congruent, "Congruent triangles must NOT contain right triangle clause c09!"

    # 等腰三角形：必须包含 c08；绝不能包含全等 c03, c04
    isosceles = cand_map["math_cand.geo.isosceles_triangle"]["source_clause_ids"]
    assert tri_c08 in isosceles
    assert tri_c03 not in isosceles and tri_c04 not in isosceles

    # 直角勾股：必须包含 c09；绝不能包含全等 c05 或角平分线 c06
    pythagoras = cand_map["math_cand.geo.pythagoras"]["source_clause_ids"]
    assert tri_c09 in pythagoras
    assert tri_c05 not in pythagoras and tri_c06 not in pythagoras

    # 相交线与角：包含角平分线 c06 与垂直平分线 c07
    lines_angles = cand_map["math_cand.geo.lines_angles"]["source_clause_ids"]
    assert tri_c06 in lines_angles
    assert tri_c07 in lines_angles

    # 三角形基本性质：包含三角形中位线定理 (quadrilateral:c04)；绝不能包含垂直平分线 c07
    tri_basic = cand_map["math_cand.geo.triangle_basic"]["source_clause_ids"]
    assert quad_c04 in tri_basic, "Triangle basic must contain triangle midline theorem quad_c04!"
    assert tri_c07 not in tri_basic

    # 3. 验证四边形条款归位
    special_quad = cand_map["math_cand.geo.special_parallelogram"]["source_clause_ids"]
    assert "cs:math:2022-errata:s4:geom:content_req:quadrilateral:c03" in special_quad
    assert quad_c04 not in special_quad, "Special parallelogram must NOT contain triangle midline quad_c04!"

    # 4. 验证统计条款分配
    samp_c04 = "cs:math:2022-errata:s4:stat_prob:content_req:sampling:c04"
    samp_c05 = "cs:math:2022-errata:s4:stat_prob:content_req:sampling:c05"
    samp_c07 = "cs:math:2022-errata:s4:stat_prob:content_req:sampling:c07"

    samp_collect = cand_map["math_cand.stat.sampling_collection"]["source_clause_ids"]
    central_disp = cand_map["math_cand.stat.central_dispersion"]["source_clause_ids"]

    # 频数直方图 c07 属于数据收集整理，不属于集中离散指标
    assert samp_c07 in samp_collect
    assert samp_c07 not in central_disp

    # 平均数/中位数/众数 c04 与方差 c05 属于集中离散度量，不属于抽样调查
    assert samp_c04 in central_disp and samp_c05 in central_disp
    assert samp_c04 not in samp_collect and samp_c05 not in samp_collect

    # 5. 验证圆与选学标记（ST-020-RM-01 专项目标断言）
    circle_c01 = "cs:math:2022-errata:s4:geom:content_req:circle:c01"
    circle_c01b = "cs:math:2022-errata:s4:geom:content_req:circle:c01b"
    circle_c02 = "cs:math:2022-errata:s4:geom:content_req:circle:c02"
    circle_c03 = "cs:math:2022-errata:s4:geom:content_req:circle:c03"
    circle_c04 = "cs:math:2022-errata:s4:geom:content_req:circle:c04"
    circle_c05 = "cs:math:2022-errata:s4:geom:content_req:circle:c05"
    circle_c06 = "cs:math:2022-errata:s4:geom:content_req:circle:c06"
    circle_c07 = "cs:math:2022-errata:s4:geom:content_req:circle:c07"
    circle_c08 = "cs:math:2022-errata:s4:geom:content_req:circle:c08"
    circle_c09 = "cs:math:2022-errata:s4:geom:content_req:circle:c09"

    circle_basic = cand_map["math_cand.geo.circle_basic"]["source_clause_ids"]
    circle_tangent = cand_map["math_cand.geo.circle_tangent"]["source_clause_ids"]
    geo_all = cand_map["math_cand.geo"]["source_clause_ids"]
    geo_prop = cand_map["math_cand.geo.properties"]["source_clause_ids"]
    arc_sector = cand_map["math_cand.geo.arc_sector"]

    # 验证 c01 与 c01b 的集合等值继承
    assert circle_c01 in circle_basic and circle_c01b in circle_basic, "circle_basic must retain both c01 and c01b!"
    assert circle_c01 in geo_all and circle_c01b in geo_all, "math_cand.geo must retain both c01 and c01b!"
    assert circle_c01 in geo_prop and circle_c01b in geo_prop, "math_cand.geo.properties must retain both c01 and c01b!"

    # 验证 c01 与 c01b 原文与属性
    assert c_map[circle_c01]["clause_number"] == "①"
    assert "探索并掌握点与圆的位置关系" in c_map[circle_c01]["raw_text"]
    assert c_map[circle_c01]["is_elective"] is False
    assert c_map[circle_c01b]["clause_number"] == "②"
    assert c_map[circle_c01b]["raw_text"] == "探索并证明垂径定理：垂直于弦的直径平分弦以及弦所对的两条弧。"
    assert c_map[circle_c01b]["is_elective"] is False
    assert c_map[circle_c01b]["review_status"] == "pending"

    # 验证 c02~c05 序号与正文修复
    assert c_map[circle_c02]["clause_number"] == "③"
    assert "圆内接四边形的对角互补" in c_map[circle_c02]["raw_text"]
    assert c_map[circle_c03]["clause_number"] == "④"
    assert c_map[circle_c04]["clause_number"] == "⑤"
    assert c_map[circle_c04]["raw_text"] == "了解直线与圆的位置关系，掌握切线的概念（例 75）。"
    assert "探索切线与过切点的半径的关系" not in c_map[circle_c04]["raw_text"], "Old 2011 text must be removed from c04!"
    assert c_map[circle_c05]["clause_number"] == "⑥"
    assert "作圆的内接正方形和内接正六边形" in c_map[circle_c05]["raw_text"]

    # 验证切线节点与选学标记 (ST-020-2B-01 选学强隔离：c06、c07 剥离至 circle_tangent_length)
    assert circle_c04 in circle_tangent, "Tangent determination c04 must belong to circle_tangent!"
    assert circle_c04 not in circle_basic
    assert circle_c05 in circle_basic, "Inscribed/circumscribed circle c05 belongs to circle_basic!"
    assert circle_c06 not in circle_tangent and circle_c07 not in circle_tangent, "c06 and c07 must be isolated from circle_tangent!"
    circle_tangent_len = cand_map["math_cand.geo.circle_tangent_length"]["source_clause_ids"]
    assert circle_c06 in circle_tangent_len and circle_c07 in circle_tangent_len, "c06 and c07 belong to elective circle_tangent_length!"
    assert c_map[circle_c06]["clause_number"] == "⑦"
    assert c_map[circle_c06]["is_elective"] is True
    assert c_map[circle_c07]["clause_number"] == "⑧"
    assert c_map[circle_c07]["is_elective"] is True

    # 验证 c08、c09 为非选学
    assert c_map[circle_c08]["clause_number"] == "⑨"
    assert c_map[circle_c08]["is_elective"] is False
    assert c_map[circle_c09]["clause_number"] == "⑩"
    assert c_map[circle_c09]["is_elective"] is False
    assert "*正多边形与圆（选学*）" not in arc_sector["description"], "Regular polygons must not be marked elective in arc_sector description!"

    # 一元二次方程根与系数关系为非选学
    quad_eq_c07 = c_map["cs:math:2022-errata:s4:num_alg:content_req:quad_eq:c07"]
    assert quad_eq_c07["is_elective"] is False
    assert "*根与系数关系" not in cand_map["math_cand.eq.quadratic"]["description"]

    # 分式方程同时包含解方程 c02 与检验合理性 c08
    frac_eq_cids = cand_map["math_cand.eq.fractional"]["source_clause_ids"]
    assert "cs:math:2022-errata:s4:num_alg:content_req:quad_eq:c02" in frac_eq_cids
    assert "cs:math:2022-errata:s4:num_alg:content_req:quad_eq:c08" in frac_eq_cids

    # 6. 验证旧考点映射中几何综合与新定义为 pending_human_review
    assert mappings["math.geo.comprehensive"]["action"] == "pending_human_review"
    assert mappings["math.adv.new_definition"]["action"] == "pending_human_review"
    assert mapping_data["summary"]["pending_human_review_count"] == 2


def test_circle_tangent_elective_isolation():
    """ST-020-2B-01 专项目标验证：数学必学切线与选学切线长定理强隔离。"""
    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        cands = json.load(f)
    cand_map = {c["code"]: c for c in cands}

    tangent = cand_map["math_cand.geo.circle_tangent"]
    assert tangent["is_elective"] is False
    assert tangent["source_clause_ids"] == ["cs:math:2022-errata:s4:geom:content_req:circle:c04"]
    assert "math.geo.circle" in tangent["legacy_mapping_codes"]

    tangent_len = cand_map["math_cand.geo.circle_tangent_length"]
    assert tangent_len["is_elective"] is True
    assert tangent_len["parent_code"] == "math_cand.geo.properties"
    assert tangent_len["level"] == 3
    assert set(tangent_len["source_clause_ids"]) == {
        "cs:math:2022-errata:s4:geom:content_req:circle:c06",
        "cs:math:2022-errata:s4:geom:content_req:circle:c07"
    }
    assert tangent_len["legacy_mapping_codes"] == []

