"""AC-GAP-03：调整规则不修改历史作答记录；画像/计划/复测是纯派生。"""
import pytest
from sqlalchemy import inspect, select

import shutong.guidance as guidance
from shutong import models as m
from shutong.database import get_db
from shutong.main import app


@pytest.fixture
def db(client):
    yield from app.dependency_overrides[get_db]()


def snapshot(record):
    return {column.key: getattr(record, column.key) for column in inspect(record).mapper.column_attrs}


def test_rule_change_rederives_without_touching_history(client, student_auth, db, published, monkeypatch):
    # 经练习流产生真实 AnswerAttempt/Exposure 行：math.arithmetic 上 3 道 evaluation，答案混合（A/A/B）。
    assert client.post("/api/goals", json={"subject": "math", "target_points": 90, "max_points": 100, "minutes_per_day": 15}, headers=student_auth).status_code == 201
    for i, answer in enumerate(["A", "A", "B"]):
        item = client.get("/api/practice/next?subject=math&purpose=evaluation&knowledge_id=math.arithmetic", headers=student_auth).json()
        r = client.post("/api/practice/attempts", json={"client_attempt_id": f"replay-{i}", "exposure_id": item["exposure_id"], "answer": answer}, headers=student_auth)
        assert r.status_code == 201
    original_model_version = guidance.MODEL_VERSION
    original_min_items = guidance.MIN_DISTINCT_ITEMS
    original_threshold = guidance.provisional_threshold
    before_plan = client.get("/api/guidance/plan?subject=math", headers=student_auth).json()
    assert before_plan["model_version"] == original_model_version
    assert before_plan["planning_threshold"] == 0.9
    attempts_before = [snapshot(r) for r in db.scalars(select(m.AnswerAttempt).order_by(m.AnswerAttempt.id)).all()]
    exposures_before = [snapshot(r) for r in db.scalars(select(m.Exposure).order_by(m.Exposure.id)).all()]
    assert len(attempts_before) == 3 and len(exposures_before) == 3

    # 模拟“调整规则”：只改运行时规则，不触碰任何数据行。
    monkeypatch.setattr(guidance, "MIN_DISTINCT_ITEMS", 2)
    monkeypatch.setattr(guidance, "MODEL_VERSION", "guidance-heuristic-v0.2-test")
    monkeypatch.setattr(guidance, "provisional_threshold", lambda target_points, max_points: 0.5)

    # 重算画像/计划/复测：输出反映新规则（纯派生）。
    profile = client.get("/api/guidance/profile?subject=math", headers=student_auth).json()
    by_topic = {k["topic"]: k for k in profile["knowledge"]}
    assert by_topic["基础算术运算"]["sample_size"] == 3  # 历史行不变，样本量仍为 3
    plan = client.get("/api/guidance/plan?subject=math", headers=student_auth).json()
    assert plan["planning_threshold"] == 0.5
    assert plan["model_version"] == "guidance-heuristic-v0.2-test"
    validation = client.get("/api/guidance/validation?subject=math", headers=student_auth)
    assert validation.status_code == 200  # 红：当前无该路由（404），Phase-2 落地后转绿
    assert validation.json()["model_version"] == "guidance-heuristic-v0.2-test"

    # 历史不可变：调整规则后，DB 行与快照逐值相等。
    db.expire_all()
    assert [snapshot(r) for r in db.scalars(select(m.AnswerAttempt).order_by(m.AnswerAttempt.id)).all()] == attempts_before
    assert [snapshot(r) for r in db.scalars(select(m.Exposure).order_by(m.Exposure.id)).all()] == exposures_before

    # 撤销规则补丁后重算：原始规则与阈值即回归，证明规则不持久化、结果可纯重放。
    # 注意：逐项恢复原值，勿用 monkeypatch.undo()——该 fixture 实例与 client fixture 共享，
    # 中途 undo 会连带撤销 SHUTONG_TOKEN 与 get_db override，使后续请求失去测试环境。
    monkeypatch.setattr(guidance, "MIN_DISTINCT_ITEMS", original_min_items)
    monkeypatch.setattr(guidance, "MODEL_VERSION", original_model_version)
    monkeypatch.setattr(guidance, "provisional_threshold", original_threshold)
    restored = client.get("/api/guidance/plan?subject=math", headers=student_auth).json()
    assert restored["model_version"] == original_model_version
    assert restored["planning_threshold"] == 0.9
