# -*- coding: utf-8 -*-
"""P0-1 阶段安全与数据隔离专项测试 (AC-SEC-02, AC-ISO-01)。

验证：
1. 管理端与学生端凭据独立配置，绝对不能相同；
2. 管理端凭据访问管理 API 成功，访问学生端 API 拦截 (403 Forbidden)；
3. 学生端凭据访问学生 API 成功，访问管理端 API 拦截 (403 Forbidden)；
4. 缺失或非法格式凭据统一拒绝 (401 Unauthorized)；
5. 学生端响应数据隔离：练习、会话恢复、计划、阶段对比、画像彻底剥离内部 knowledge_id，
   且仅呈现自然语言领域主题与提升建议，零内部知识编码泄露。
"""
from __future__ import annotations

import pytest


def test_admin_token_access_admin_api_success(client, admin_auth):
    """正例：管理凭据可正常访问管理 API 与题库体检、学校考试。"""
    res = client.get("/api/admin/verify", headers=admin_auth)
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "role": "admin"}

    res = client.get("/api/guidance/pool-health?subject=math", headers=admin_auth)
    assert res.status_code == 200

    res = client.get("/api/school-exams?subject=math", headers=admin_auth)
    assert res.status_code == 200


def test_student_token_access_student_api_success(client, student_auth, published):
    """正例：学生凭据可正常访问学生端各功能接口。"""
    res = client.get("/api/student/verify", headers=student_auth)
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "role": "student"}

    res = client.get("/api/subjects", headers=student_auth)
    assert res.status_code == 200
    assert "math" in res.json()

    res = client.get("/api/practice/next?subject=math&purpose=training", headers=student_auth)
    assert res.status_code == 200

    # 设定目标后获取学习计划
    client.post("/api/goals", json={"subject": "math", "target_points": 90, "max_points": 100, "minutes_per_day": 15}, headers=student_auth)
    res = client.get("/api/guidance/plan?subject=math", headers=student_auth)
    assert res.status_code == 200


def test_student_token_access_admin_api_rejected(client, student_auth, published):
    """越权防御：学生凭据调用管理 API（来源、原件、体检、校考）必须被 403 明确拒绝。"""
    res = client.get("/api/admin/verify", headers=student_auth)
    assert res.status_code == 403
    assert "Admin authorization required; student token not permitted" in res.json()["detail"]

    res = client.get("/api/admin/sources", headers=student_auth)
    assert res.status_code == 403

    res = client.post("/api/admin/sources", json={"title": "越权题源", "subject": "math"}, headers=student_auth)
    assert res.status_code == 403

    res = client.get("/api/guidance/pool-health?subject=math", headers=student_auth)
    assert res.status_code == 403

    res = client.get("/api/school-exams?subject=math", headers=student_auth)
    assert res.status_code == 403

    res = client.post("/api/school-exams", json={"subject": "math", "title": "越权卷", "exam_date": "2026-11-07", "earned_points": 90, "max_points": 100, "confirmed_by_user": True}, headers=student_auth)
    assert res.status_code == 403


def test_admin_token_access_student_api_rejected(client, admin_auth, published):
    """互换防御：管理凭据不可互换作为学生凭据调用学生专属 API，必须被 403 明确拒绝。"""
    res = client.get("/api/student/verify", headers=admin_auth)
    assert res.status_code == 403
    assert "Student authorization required; admin token not permitted" in res.json()["detail"]

    res = client.get("/api/subjects", headers=admin_auth)
    assert res.status_code == 403

    res = client.get("/api/practice/next?subject=math&purpose=training", headers=admin_auth)
    assert res.status_code == 403

    res = client.get("/api/practice/resume?subject=math", headers=admin_auth)
    assert res.status_code == 403

    res = client.get("/api/guidance/plan?subject=math", headers=admin_auth)
    assert res.status_code == 403

    res = client.get("/api/guidance/profile?subject=math", headers=admin_auth)
    assert res.status_code == 403

    res = client.get("/api/guidance/validation?subject=math", headers=admin_auth)
    assert res.status_code == 403


def test_unauthenticated_or_invalid_tokens_rejected(client):
    """负例：未提供凭据或凭据无效必须返回 401 Unauthorized。"""
    assert client.get("/api/admin/verify").status_code == 401
    assert client.get("/api/student/verify").status_code == 401
    assert client.get("/api/subjects").status_code == 401

    invalid_header = {"Authorization": "Bearer wrong-token"}
    assert client.get("/api/admin/verify", headers=invalid_header).status_code == 401
    assert client.get("/api/student/verify", headers=invalid_header).status_code == 401
    assert client.get("/api/subjects", headers=invalid_header).status_code == 401

    basic_header = {"Authorization": "Basic dXNlcjpwYXNz"}
    assert client.get("/api/admin/verify", headers=basic_header).status_code == 401
    assert client.get("/api/student/verify", headers=basic_header).status_code == 401


def test_identical_tokens_configuration_rejected(client, monkeypatch):
    """配置防御：若服务端配置了相同的管理凭据与学生凭据，必须 503 拒绝服务。"""
    monkeypatch.setenv("SHUTONG_ADMIN_TOKEN", "shared-identical-secret")
    monkeypatch.setenv("SHUTONG_STUDENT_TOKEN", "shared-identical-secret")
    header = {"Authorization": "Bearer shared-identical-secret"}

    res = client.get("/api/admin/verify", headers=header)
    assert res.status_code == 503
    assert "must not be identical" in res.json()["detail"]

    res = client.get("/api/student/verify", headers=header)
    assert res.status_code == 503
    assert "must not be identical" in res.json()["detail"]


def test_student_api_data_isolation_cleanliness(client, admin_auth, student_auth, published):
    """数据隔离断言：学生端所有 API 响应绝不泄露内部 knowledge_id 及内部知识库编码。"""
    # 1. 练习取题 next
    next_res = client.get("/api/practice/next?subject=math&purpose=training", headers=student_auth)
    assert next_res.status_code == 200
    next_data = next_res.json()
    assert "knowledge_ids" not in next_data, "学生取题接口严禁暴露 knowledge_ids"
    assert "knowledge_id" not in next_data, "学生取题接口严禁暴露 knowledge_id"

    # 2. 会话恢复 resume
    eval_item = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth).json()
    resume_res = client.get("/api/practice/resume?subject=math", headers=student_auth)
    assert resume_res.status_code == 200
    resume_data = resume_res.json()
    assert resume_data["item"] is not None
    assert "knowledge_ids" not in resume_data["item"], "学生续答接口严禁暴露 knowledge_ids"

    # 3. 学习计划 plan
    client.post("/api/goals", json={"subject": "math", "target_points": 90, "max_points": 100, "minutes_per_day": 15}, headers=student_auth)
    plan_res = client.get("/api/guidance/plan?subject=math", headers=student_auth)
    assert plan_res.status_code == 200
    plan_data = plan_res.json()
    for step in plan_data["steps"]:
        assert "knowledge_id" not in step, "学生学习计划严禁暴露内部 knowledge_id"
        assert "topic" in step, "学生学习计划必须提供面向学生的自然语言领域主题"
        assert "advice" in step, "学生学习计划必须提供面向学生的自然语言提升建议"
        assert not step["topic"].startswith("math."), f"主题名称不能是原始内部代号：{step['topic']}"

    # 4. 学习画像 profile
    profile_res = client.get("/api/guidance/profile?subject=math", headers=student_auth)
    assert profile_res.status_code == 200
    profile_data = profile_res.json()
    for item in profile_data["knowledge"]:
        assert "knowledge_id" not in item, "学生画像接口严禁暴露内部 knowledge_id"
        assert "topic" in item, "学生画像接口必须提供自然语言领域主题"

    # 5. 阶段对比 validation
    val_res = client.get("/api/guidance/validation?subject=math", headers=student_auth)
    assert val_res.status_code == 200
    val_data = val_res.json()
    for item in val_data["knowledge"]:
        assert "knowledge_id" not in item, "阶段对比接口严禁暴露内部 knowledge_id"
        assert "topic" in item, "阶段对比接口必须提供自然语言领域主题"
