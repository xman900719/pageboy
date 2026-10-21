"""ST-005：使用虚构测试数据验证数学纵向闭环（目标→诊断→差距→计划→复练→未见题复测）。"""
import pytest
from sqlalchemy import func, select

from shutong import models as m
from shutong.database import get_db
from shutong.main import app


@pytest.fixture
def db(client):
    yield from app.dependency_overrides[get_db]()


@pytest.fixture
def math_pool(client, auth):
    """一个已核实来源 + 三个虚构知识点的已发布单选题池（全部虚构测试数据）。

    题量按曝光纪律反推：evaluation 只发未见题、training 按（最少曝光优先）轮换会消耗未见过的新题，
    因此每个需要 N 道“全新未见 evaluation”的阶段都要预留独立题目：
    - math.gap 9 道：诊断×3 + 复练×3（新题）+ 复测×3；
    - math.ok 8 道：仅用于提示污染反例（3 道 evaluation）；
    - math.sparse 4 道：基线×3 + 复测×1。
    （设计规格 §5 的“各 ≥8 道”允许此规模；8 道会让 math.gap 第 3 道复测 evaluation 落 404。）
    """
    src = client.post("/api/admin/sources", json={
        "title": "虚构测试数据：数学纵向闭环题源", "subject": "math",
        "rights_status": "personal_use_reviewed", "verified": True}, headers=auth).json()["id"]
    published_ids = {}
    for knowledge_id, count, label in (("math.gap", 9, "短板"), ("math.ok", 8, "对照"), ("math.sparse", 4, "稀疏")):
        ids = []
        for i in range(count):
            q = client.post("/api/admin/questions", json={
                "source_document_id": src,
                "stem": f"虚构测试数据：{label}考点 {knowledge_id} 第{i + 1}题：1+1 等于几？",
                "options": ["A. 1", "B. 2"], "correct_answer": "B",
                "knowledge_ids": [knowledge_id], "max_points": 2}, headers=auth)
            assert q.status_code == 201
            version_id = q.json()["id"]
            assert client.post(f"/api/admin/questions/{version_id}/review", headers=auth).status_code == 200
            assert client.post(f"/api/admin/questions/{version_id}/publish", headers=auth).status_code == 200
            ids.append(version_id)
        published_ids[knowledge_id] = ids
    return published_ids


def test_math_vertical_loop(client, auth, db, math_pool):
    exposures_created = 0
    attempts_recorded = 0

    def next_item(purpose=None, knowledge_id=None):
        nonlocal exposures_created
        path = "/api/practice/next?subject=math"
        if purpose:
            path += f"&purpose={purpose}"
        if knowledge_id:
            path += f"&knowledge_id={knowledge_id}"
        r = client.get(path, headers=auth)
        assert r.status_code == 200, r.text
        exposures_created += 1
        return r.json()

    def submit(cid, item, answer, hints=False):
        nonlocal attempts_recorded
        r = client.post("/api/practice/attempts", json={
            "client_attempt_id": cid, "exposure_id": item["exposure_id"],
            "answer": answer, "hints_used": hints}, headers=auth)
        assert r.status_code == 201, r.text
        attempts_recorded += 1
        return r.json()

    # 1) 目标
    goal = client.post("/api/goals", json={"subject": "math", "target_points": 90, "max_points": 100, "minutes_per_day": 15}, headers=auth)
    assert goal.status_code == 201

    # 2) 空状态：缺证据 = 证据不足/不可比，不是错误，更不是 0 分
    empty_profile = client.get("/api/guidance/profile?subject=math", headers=auth).json()
    assert empty_profile["knowledge"] == []
    empty_plan = client.get("/api/guidance/plan?subject=math", headers=auth).json()
    empty_steps = {s["knowledge_id"]: s for s in empty_plan["steps"]}
    assert empty_steps["math.gap"]["gap_type"] == "INSUFFICIENT_EVIDENCE"
    assert empty_steps["math.ok"]["gap_type"] == "INSUFFICIENT_EVIDENCE"
    assert "observed_rate" not in empty_steps["math.gap"]  # 缺证据绝不能呈现为 0 分
    empty_validation = client.get("/api/guidance/validation?subject=math", headers=auth)
    assert empty_validation.status_code == 200  # 红：当前无该路由（404）；无证据 ≠ 错误
    assert empty_validation.json()["verdict"] == "CANNOT_COMPARE"
    assert empty_validation.json()["knowledge"] == []

    # 3) math.gap 诊断：3 道未见 evaluation，全部答错（正确答案 'B'，作答 'A'）
    diag_ids = []
    for i in range(3):
        item = next_item(purpose="evaluation", knowledge_id="math.gap")
        assert item["unseen_at_exposure"] is True
        assert item["knowledge_ids"] == ["math.gap"]
        result = submit(f"diag-{i}", item, "A")
        assert result["earned_points"] == 0
        assert result["evaluation_valid_unseen"] is True  # 无提示 + 未见 + evaluation
        diag_ids.append(item["question_version_id"])

    # 4) 差距与计划：观察率 0 < 阈值 0.9 → KNOWLEDGE_GAP；对照知识点证据不足
    plan = client.get("/api/guidance/plan?subject=math", headers=auth).json()
    assert plan["planning_threshold"] == 0.9
    steps = {s["knowledge_id"]: s for s in plan["steps"]}
    gap = steps["math.gap"]
    assert gap["gap_type"] == "KNOWLEDGE_GAP"
    assert gap["action"] == "targeted_practice_then_unseen_evaluation"
    assert gap["observed_rate"] == 0  # 观察率 0 < 阈值 0.9
    assert steps["math.ok"]["gap_type"] == "INSUFFICIENT_EVIDENCE"
    assert steps["math.ok"]["priority"] == 0

    # 5) math.gap 复练：training 按（最少曝光优先）轮换、允许重复；完成 曝光+作答 循环即可
    for i in range(3):
        item = next_item(knowledge_id="math.gap")
        submit(f"train-{i}", item, "B")

    # 6) math.gap 复测：3 道全新未见 evaluation，全部答对；与诊断题集不相交（曝光纪律保证不复用旧题）
    retest_ids = []
    for i in range(3):
        item = next_item(purpose="evaluation", knowledge_id="math.gap")
        assert item["unseen_at_exposure"] is True
        result = submit(f"retest-{i}", item, "B")
        assert result["earned_points"] == 2
        assert result["evaluation_valid_unseen"] is True
        retest_ids.append(item["question_version_id"])
    assert set(retest_ids).isdisjoint(diag_ids)

    # 7) 复测判决：可比范围内 improved；不得给出分数预测；必须含免责声明
    validation = client.get("/api/guidance/validation?subject=math", headers=auth)
    assert validation.status_code == 200  # 红：当前 404
    report = validation.json()
    assert report["verdict"] == "IMPROVED_ON_COMPARABLE_SCOPE"
    assert report["comparable"] is True
    assert report["score_prediction"] is None
    assert report["disclaimer"]  # 非空免责声明
    kids = {e["knowledge_id"]: e for e in report["knowledge"]}
    assert set(kids) == {"math.gap"}  # math.ok / math.sparse 两端皆无证据 → 不列入
    entry = kids["math.gap"]
    assert entry["verdict"] == "improved"
    assert entry["baseline_rate"] == 0 and entry["retest_rate"] == 1
    assert entry["baseline_items"] == 3 and entry["retest_items"] == 3

    # 8) 提示污染反例：math.ok 带 hints_used=true 的 evaluation 作答不进比较样本
    for i in range(3):
        item = next_item(purpose="evaluation", knowledge_id="math.ok")
        result = submit(f"contam-{i}", item, "A", hints=True)
        assert result["evaluation_valid_unseen"] is False  # 带提示 → 非独立，不得算作有效复测
    contaminated = client.get("/api/guidance/validation?subject=math", headers=auth).json()
    assert "math.ok" not in {e["knowledge_id"] for e in contaminated["knowledge"]}  # 视同缺席
    assert contaminated["verdict"] == "IMPROVED_ON_COMPARABLE_SCOPE"  # 总判决不受污染影响
    contaminated_profile = client.get("/api/guidance/profile?subject=math", headers=auth).json()
    assert "math.ok" not in {e["knowledge_id"] for e in contaminated_profile["knowledge"]}  # summarize 已过滤

    # 9) 复测侧不足反例：math.sparse 基线 3 条全对 + 复测仅 1 条 → cannot_compare(insufficient_retest)
    for i in range(3):
        item = next_item(purpose="evaluation", knowledge_id="math.sparse")
        assert item["unseen_at_exposure"] is True
        assert submit(f"sparse-base-{i}", item, "B")["evaluation_valid_unseen"] is True
    item = next_item(purpose="evaluation", knowledge_id="math.sparse")
    assert submit("sparse-retest-0", item, "B")["evaluation_valid_unseen"] is True
    final = client.get("/api/guidance/validation?subject=math", headers=auth).json()
    final_kids = {e["knowledge_id"]: e for e in final["knowledge"]}
    assert set(final_kids) == {"math.gap", "math.sparse"}  # math.ok 仅有带提示证据 → 仍缺席
    assert [e["knowledge_id"] for e in final["knowledge"]] == ["math.gap", "math.sparse"]  # knowledge 按 id 排序
    sparse = final_kids["math.sparse"]
    assert sparse["verdict"] == "cannot_compare"
    assert sparse["reason"] == "insufficient_retest"  # 复测样本 1 < MIN_DISTINCT_ITEMS(3)
    assert final["verdict"] == "IMPROVED_ON_COMPARABLE_SCOPE"  # 总判决仍只由可比范围（math.gap）决定
    assert final["comparable"] is True

    # 10) 全程无幻影写入：行数与练习接口实际调用次数逐一致
    assert db.scalar(select(func.count()).select_from(m.Exposure)) == exposures_created
    assert db.scalar(select(func.count()).select_from(m.AnswerAttempt)) == attempts_recorded
