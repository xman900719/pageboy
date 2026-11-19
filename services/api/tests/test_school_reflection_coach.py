"""ST-023：校考「书童陪你想」苏格拉底对话复盘正反例测试（全部使用虚构测试数据）。"""

from __future__ import annotations


def _seed_exam_with_lost_item(client, auth, *, title: str = "虚构测试数据：校考书童对话"):
    res = client.post(
        "/api/school-exams",
        json={
            "subject": "math",
            "title": title,
            "exam_date": "2026-10-28",
            "earned_points": 92,
            "max_points": 100,
            "confirmed_by_user": True,
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    exam_id = res.json()["id"]
    items_res = client.post(
        f"/api/school-exams/{exam_id}/items",
        json={
            "items": [
                {
                    "question_label": "第1题",
                    "knowledge_id": "math_cand.num.rational",
                    "earned_points": 2.0,
                    "max_points": 2.0,
                    "scoring_origin": "manual_entry",
                },
                {
                    "question_label": "第8题",
                    "knowledge_id": "math_cand.eq.fractional",
                    "earned_points": 1.0,
                    "max_points": 4.0,
                    "scoring_origin": "manual_entry",
                },
            ]
        },
        headers=auth,
    )
    assert items_res.status_code == 201, items_res.text
    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    by_lbl = {it["question_label"]: it for it in detail["items"]}
    return exam_id, by_lbl["第1题"]["id"], by_lbl["第8题"]["id"]


def test_school_reflection_coach_full_flow_guards_and_admin_readonly(client, auth, student_auth, monkeypatch):
    """覆盖：权限隔离、无Key降级、无题干禁编造、幂等开场、防泄题守卫、防代写整理、管理端只读与级联删除。"""
    from shutong import ai_tutor

    exam_id, full_id, lost_id = _seed_exam_with_lost_item(client, auth)

    # 1. 权限与题型边界：管理端不可调学生端接口；学生端不可调管理端只读接口；满分题不可开启
    assert client.get(f"/api/student/school-exam-reflections/{lost_id}/coach", headers=auth).status_code == 403
    assert client.get(f"/api/school-exams/{exam_id}/items/{lost_id}/coach", headers=student_auth).status_code == 403
    assert client.post(f"/api/student/school-exam-reflections/{full_id}/coach/start", json={}, headers=student_auth).status_code == 422

    # 2. 未配置 Key 时优雅返回 503 COACH_NOT_CONFIGURED，且 GET 零 AI 调用
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    get_empty = client.get(f"/api/student/school-exam-reflections/{lost_id}/coach", headers=student_auth)
    assert get_empty.status_code == 200
    assert get_empty.json()["started"] is False
    assert get_empty.json()["turns"] == []

    no_key = client.post(f"/api/student/school-exam-reflections/{lost_id}/coach/start", json={}, headers=student_auth)
    assert no_key.status_code == 503
    assert no_key.json()["detail"] == "COACH_NOT_CONFIGURED"

    # 3. 暂存未确认题干（绝不能进入书童上下文）+ 验证无题干诚实约束与幂等开启
    client.patch(
        f"/api/school-exams/{exam_id}/items/{lost_id}/stem",
        json={"stem_text": "未确认草稿题干不应泄露", "confirm": False},
        headers=auth,
    )
    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test-coach")
    captured_prompts: list[str] = []
    reply_queue = [
        ("你好！我暂时看不到原卷文字，你能先说说这道题问什么、你第一步怎么想的吗？", "deepseek-chat"),
        ("正确答案是 x=3，所以选 B。", "deepseek-chat"),  # 触发防泄题守卫
        ("抓到关键啦！那下次遇到分式方程，你打算给自己定一个什么小动作防踩坑？", "deepseek-chat"),
    ]

    def fake_chat(messages, **kwargs):
        captured_prompts.append(messages[0]["content"])
        if kwargs.get("response_format") == {"type": "json_object"}:
            return (
                '{"error_category":"method","stuck_point":"去分母后忘了检验分母不为零导致多留增根","fix_strategy":"如果再看到分式方程，我就先写清分母不为零并在解出后逐一代回验根。"}',
                "deepseek-chat",
            )
        return reply_queue.pop(0)

    monkeypatch.setattr(ai_tutor, "_post_chat_completion", fake_chat)

    s1 = client.post(
        f"/api/student/school-exam-reflections/{lost_id}/coach/start",
        json={"scene_hint": "stuck_midway"},
        headers=student_auth,
    )
    assert s1.status_code == 200, s1.text
    assert s1.json()["started"] is True
    assert len(s1.json()["turns"]) == 1
    assert "未确认草稿题干不应泄露" not in captured_prompts[0]
    assert "绝不可以猜测或编造" in captured_prompts[0]
    assert "math_cand" not in captured_prompts[0]

    # 幂等：再次调用 /start 直接返回已有对话，不重复调用 AI
    s1_again = client.post(f"/api/student/school-exam-reflections/{lost_id}/coach/start", json={}, headers=student_auth)
    assert s1_again.status_code == 200
    assert len(captured_prompts) == 1

    # 4. 家长确认题干与作答后，后续轮次即可使用已确认题干，且测试防泄题守卫拦截
    client.patch(
        f"/api/school-exams/{exam_id}/items/{lost_id}/stem",
        json={"stem_text": "解分式方程 $\\frac{1}{x-2}=1$", "student_answer_text": "解得 x=2", "confirm": True},
        headers=auth,
    )
    m1 = client.post(
        f"/api/student/school-exam-reflections/{lost_id}/coach/message",
        json={"content": "我去分母之后直接算出结果就交卷了"},
        headers=student_auth,
    )
    assert m1.status_code == 200, m1.text
    assert "解分式方程" in captured_prompts[1]
    assert "解得 x=2" in captured_prompts[1]
    last_turn = m1.json()["turns"][-1]
    assert last_turn["sanitized_guard_triggered"] is True
    assert "正确答案是" not in last_turn["content"]
    assert m1.json()["can_summarize"] is False

    # 仅 1 轮学生发言时整理草稿必须被 422 拦截
    too_short = client.post(f"/api/student/school-exam-reflections/{lost_id}/coach/summarize", headers=student_auth)
    assert too_short.status_code == 422
    assert too_short.json()["detail"] == "COACH_DIALOGUE_TOO_SHORT"

    # 第 2 轮学生发言后允许整理草稿，但绝不自动提交复盘
    m2 = client.post(
        f"/api/student/school-exam-reflections/{lost_id}/coach/message",
        json={"content": "忘了把解代回分母检验增根，下次解完分式方程立刻代回原分母验算"},
        headers=student_auth,
    )
    assert m2.status_code == 200, m2.text
    assert m2.json()["can_summarize"] is True

    sum_res = client.post(f"/api/student/school-exam-reflections/{lost_id}/coach/summarize", headers=student_auth)
    assert sum_res.status_code == 200, sum_res.text
    draft = sum_res.json()["draft_summary"]
    assert draft["error_category"] == "method"
    assert "增根" in draft["stuck_point"]
    assert "验根" in draft["fix_strategy"]
    assert draft["ready"] is True

    # 校验小题本身仍为 pending（书童绝不替学生自动提交复盘）
    stu_list = client.get("/api/student/school-exam-reflections?subject=math", headers=student_auth).json()
    q8_stu = next(x for x in stu_list["items"] if x["item_id"] == lost_id)
    assert q8_stu["reflection_status"] == "pending"
    assert q8_stu["coach_turn_count"] == 5

    # 5. 管理端可只读查看学生与书童的完整对话及计数
    admin_detail = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    q8_admin = next(x for x in admin_detail["items"] if x["id"] == lost_id)
    assert q8_admin["coach_turn_count"] == 5

    admin_coach = client.get(f"/api/school-exams/{exam_id}/items/{lost_id}/coach", headers=auth)
    assert admin_coach.status_code == 200
    assert len(admin_coach.json()["turns"]) == 5

    # 6. 删除校考可安全级联清理书童会话与轮次
    del_res = client.delete(f"/api/school-exams/{exam_id}?confirm=true", headers=auth)
    assert del_res.status_code == 200, del_res.text


def test_school_reflection_coach_enforces_turn_limit(client, auth, student_auth, monkeypatch):
    """单题用户发言超过 12 轮上限后返回 409 COACH_TURN_LIMIT_REACHED。"""
    from shutong import ai_tutor

    _exam_id, _full_id, lost_id = _seed_exam_with_lost_item(client, auth, title="虚构测试数据：书童轮次上限")
    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test-coach")
    monkeypatch.setattr(ai_tutor, "_post_chat_completion", lambda messages, **kw: ("继续说说你的下一步思路？", "deepseek-chat"))

    for idx in range(12):
        r = client.post(
            f"/api/student/school-exam-reflections/{lost_id}/coach/message",
            json={"content": f"第 {idx + 1} 轮思考内容"},
            headers=student_auth,
        )
        assert r.status_code == 200, r.text

    overflow = client.post(
        f"/api/student/school-exam-reflections/{lost_id}/coach/message",
        json={"content": "第 13 轮超限发言"},
        headers=student_auth,
    )
    assert overflow.status_code == 409
    assert overflow.json()["detail"] == "COACH_TURN_LIMIT_REACHED"
