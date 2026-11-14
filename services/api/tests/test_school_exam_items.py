"""ST-006：使用虚构测试数据验证学校私卷逐题得分确认与考点证据门禁（AC-EVI-01/02）。"""


def make_exam(client, auth, **overrides):
    body = {"subject": "math", "title": "虚构测试数据：周测", "exam_date": "2026-10-20",
            "earned_points": 72, "max_points": 100, "confirmed_by_user": True}
    body.update(overrides)
    response = client.post("/api/school-exams", json=body, headers=auth)
    assert response.status_code == 201
    return response.json()["id"]


def item(question_label, knowledge_id="math.arithmetic", earned_points=2.0, max_points=2.0, scoring_origin="manual_entry"):
    return {"question_label": question_label, "knowledge_id": knowledge_id, "earned_points": earned_points,
            "max_points": max_points, "scoring_origin": scoring_origin}


def post_items(client, auth, exam_id, items):
    return client.post(f"/api/school-exams/{exam_id}/items", json={"items": items}, headers=auth)


def confirm_item(client, auth, exam_id, item_id, earned_points, confirmed_by_human=True):
    return client.post(f"/api/school-exams/{exam_id}/items/{item_id}/confirm",
                       json={"confirmed_by_human": confirmed_by_human, "earned_points": earned_points}, headers=auth)


def profile_knowledge(client, student_auth, subject="math"):
    response = client.get(f"/api/guidance/profile?subject={subject}", headers=student_auth)
    assert response.status_code == 200
    return response.json()["knowledge"]


def knowledge_entry(topic, entries):
    return next((e for e in entries if e["topic"] == topic), None)


def test_totals_never_create_knowledge_evidence(client, auth, student_auth):
    # AC-EVI-01 回归：仅录入总分（即使人工确认）也绝不产生考点证据。
    created = client.post("/api/school-exams", json={
        "subject": "math", "title": "虚构测试数据：周测", "exam_date": "2026-10-20",
        "earned_points": 72, "max_points": 100, "confirmed_by_user": True}, headers=auth)
    assert created.status_code == 201
    assert created.json()["knowledge_evidence_created"] is False
    assert profile_knowledge(client, student_auth) == []


def test_confirmed_items_create_evidence_not_totals(client, auth, student_auth, published):
    exam_id = make_exam(client, auth)
    posted = post_items(client, auth, exam_id, [item("第5题")])
    assert posted.status_code == 201
    body = posted.json()
    assert body["items"][0]["confirmed_by_user"] is True  # manual_entry 人工录入即人工确认
    assert body["evidence_created"] == 1
    knowledge = profile_knowledge(client, student_auth)
    assert len(knowledge) == 1
    assert knowledge[0]["topic"] == "基础算术运算"
    assert knowledge[0]["sample_size"] == 1
    assert knowledge[0]["observed_rate"] == 1.0  # 证据来自该题 2/2，与总分 72/100 无关（INV-05）
    # 规划消费同一证据装配：1 条样本必然显示“证据不足”，补足 3 条确认 item 后才能观察到规划变化。
    goal = client.post("/api/goals", json={"subject": "math", "target_points": 90, "max_points": 100,
                                           "minutes_per_day": 15}, headers=student_auth)
    assert goal.status_code == 201
    more = post_items(client, auth, exam_id, [item("第6题"), item("第7题")])
    assert more.status_code == 201 and more.json()["evidence_created"] == 2
    assert profile_knowledge(client, student_auth)[0]["sample_size"] == 3
    plan = client.get("/api/guidance/plan?subject=math", headers=student_auth).json()
    step = next(s for s in plan["steps"] if s["topic"] == "基础算术运算")
    assert step["gap_type"] == "NO_CONFIRMED_GAP"  # 若校卷 item 不进证据装配，将仍是 INSUFFICIENT_EVIDENCE


def test_ocr_draft_items_do_not_create_evidence_until_confirmed(client, auth, student_auth):
    # AC-EVI-02：未经人工核对的 OCR 草稿不得进入确认得分，也不产生证据。
    exam_id = make_exam(client, auth)
    posted = post_items(client, auth, exam_id, [
        item("第1题", knowledge_id="math.geometry", earned_points=3.0, max_points=4.0, scoring_origin="ocr_draft"),
        item("第2题", knowledge_id="math.geometry", earned_points=1.0, max_points=4.0, scoring_origin="ocr_draft"),
    ])
    assert posted.status_code == 201
    body = posted.json()
    assert [i["confirmed_by_user"] for i in body["items"]] == [False, False]
    assert body["evidence_created"] == 0
    assert knowledge_entry("几何图形与推理证明", profile_knowledge(client, student_auth)) is None
    first_id, second_id = body["items"][0]["id"], body["items"][1]["id"]
    confirmed_first = confirm_item(client, auth, exam_id, first_id, earned_points=3.0)
    assert confirmed_first.status_code == 200
    assert confirmed_first.json()["confirmed_by_user"] is True
    assert confirmed_first.json()["scoring_origin"] == "ocr_draft"  # INV-04：确认后原始来源保留
    confirmed_second = confirm_item(client, auth, exam_id, second_id, earned_points=2.0)  # 人工核对修正识别分 1→2
    assert confirmed_second.status_code == 200
    assert confirmed_second.json()["confirmed_by_user"] is True
    assert confirmed_second.json()["scoring_origin"] == "ocr_draft"
    geometry = knowledge_entry("几何图形与推理证明", profile_knowledge(client, student_auth))
    assert geometry is not None
    assert geometry["sample_size"] == 2
    assert geometry["observed_rate"] == 0.625  # (3+2)/(4+4)


def test_confirm_requires_human_flag_and_bounds(client, auth):
    exam_id = make_exam(client, auth)
    posted = post_items(client, auth, exam_id, [
        item("第1题", knowledge_id="math.geometry", earned_points=1.0, max_points=4.0, scoring_origin="ocr_draft")])
    assert posted.status_code == 201
    draft_id = posted.json()["items"][0]["id"]
    assert confirm_item(client, auth, exam_id, draft_id, earned_points=3.0, confirmed_by_human=False).status_code == 422
    assert confirm_item(client, auth, exam_id, draft_id, earned_points=5.0).status_code == 422  # 5 > item.max_points 4
    assert confirm_item(client, auth, exam_id, "missing-item", earned_points=1.0).status_code == 404
    other_exam_id = make_exam(client, auth)
    assert confirm_item(client, auth, other_exam_id, draft_id, earned_points=3.0).status_code == 404  # item 不属于该考试


def test_confirmed_items_are_immutable(client, auth):
    # 确认后不可变：改判须另建记录，历史不静默改写。
    exam_id = make_exam(client, auth)
    manual = post_items(client, auth, exam_id, [item("第5题")])
    assert manual.status_code == 201
    manual_id = manual.json()["items"][0]["id"]
    repeat = confirm_item(client, auth, exam_id, manual_id, earned_points=2.0)
    assert repeat.status_code == 409 and repeat.json()["detail"] == "SCHOOL_ITEM_ALREADY_CONFIRMED"
    draft = post_items(client, auth, exam_id, [
        item("第6题", earned_points=1.0, max_points=4.0, scoring_origin="ocr_draft")])
    assert draft.status_code == 201
    draft_id = draft.json()["items"][0]["id"]
    assert confirm_item(client, auth, exam_id, draft_id, earned_points=3.0).status_code == 200
    again = confirm_item(client, auth, exam_id, draft_id, earned_points=3.0)
    assert again.status_code == 409 and again.json()["detail"] == "SCHOOL_ITEM_ALREADY_CONFIRMED"
    changed = confirm_item(client, auth, exam_id, draft_id, earned_points=1.0)
    assert changed.status_code == 409 and changed.json()["detail"] == "SCHOOL_ITEM_IMMUTABLE"


def test_manual_entry_requires_confirmation_semantics(client, auth):
    # manual_entry 录入即人工确认；不存在经由 items POST 的“补确认”路径，confirm 只会撞已确认。
    exam_id = make_exam(client, auth)
    posted = post_items(client, auth, exam_id, [item("第5题")])
    assert posted.status_code == 201
    assert posted.json()["items"][0]["confirmed_by_user"] is True
    assert posted.json()["evidence_created"] == 1
    conflict = confirm_item(client, auth, exam_id, posted.json()["items"][0]["id"], earned_points=2.0)
    assert conflict.status_code == 409 and conflict.json()["detail"] == "SCHOOL_ITEM_ALREADY_CONFIRMED"


def test_item_input_validation_and_duplicates(client, auth):
    exam_id = make_exam(client, auth)
    assert post_items(client, auth, exam_id, []).status_code == 422
    assert post_items(client, auth, exam_id, [item("第1题", earned_points=5.0, max_points=4.0)]).status_code == 422
    unknown_origin = dict(item("第1题"), scoring_origin="machine_guess")
    assert post_items(client, auth, exam_id, [unknown_origin]).status_code == 422
    assert post_items(client, auth, exam_id, [item("")]).status_code == 422
    conflict = post_items(client, auth, exam_id, [item("第1题"), item("第1题")])
    assert conflict.status_code == 409 and conflict.json()["detail"] == "SCHOOL_ITEM_LABEL_CONFLICT"
    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth)
    assert detail.status_code == 200 and detail.json()["items"] == []  # 整批拒绝，无部分写入
    assert post_items(client, auth, exam_id, [item("第1题")]).status_code == 201
    second = post_items(client, auth, exam_id, [item("第1题", earned_points=1.0)])
    assert second.status_code == 409 and second.json()["detail"] == "SCHOOL_ITEM_LABEL_CONFLICT"
    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth)
    assert detail.status_code == 200 and len(detail.json()["items"]) == 1


def test_items_require_owner_and_auth(client, auth):
    exam_id = make_exam(client, auth)
    unauthenticated = client.post(f"/api/school-exams/{exam_id}/items", json={"items": [item("第5题")]})
    assert unauthenticated.status_code == 401
    assert post_items(client, auth, "missing-exam", [item("第5题")]).status_code == 404
    assert post_items(client, auth, exam_id, [item("第5题")]).status_code == 201
    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth)
    assert detail.status_code == 200
    body = detail.json()
    for key in ("id", "title", "exam_date", "earned_points", "max_points", "confirmed_by_user"):
        assert key in body, key
    assert body["id"] == exam_id and body["title"] == "虚构测试数据：周测"
    assert len(body["items"]) == 1
    for key in ("id", "question_label", "knowledge_id", "earned_points", "max_points", "scoring_origin", "confirmed_by_user"):
        assert key in body["items"][0], key
    assert body["items"][0]["question_label"] == "第5题"
    assert body["items"][0]["confirmed_by_user"] is True


def test_school_and_practice_evidence_merge(client, auth, student_auth, published):
    # 已确认校卷 item 与练习评测证据合并入画像且独立计数；校卷 item 不得泄入复测装配。
    for i in range(3):
        served = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth)
        assert served.status_code == 200
        recorded = client.post("/api/practice/attempts",
                               json={"client_attempt_id": f"mix-{i}", "exposure_id": served.json()["exposure_id"],
                                     "answer": "B"}, headers=student_auth)
        assert recorded.status_code == 201
    exam_id = make_exam(client, auth)
    posted = post_items(client, auth, exam_id, [item("第1题")])
    assert posted.status_code == 201 and posted.json()["evidence_created"] == 1
    arithmetic = knowledge_entry("基础算术运算", profile_knowledge(client, student_auth))
    assert arithmetic is not None
    assert arithmetic["sample_size"] == 4  # 3 练习评测 + 1 校卷 item，合成键保证按 item 独立计数
    assert arithmetic["observed_rate"] == 1.0
    report = client.get("/api/guidance/validation?subject=math", headers=student_auth).json()
    assert report["verdict"] == "CANNOT_COMPARE"
    assert len(report["knowledge"]) == 1
    only = report["knowledge"][0]
    assert only["topic"] == "基础算术运算"
    assert only["verdict"] == "cannot_compare" and only["reason"] == "insufficient_retest"
    assert only["baseline_items"] == 3 and only["retest_items"] == 0  # 若校卷 item 泄入，retest_items 会是 1


def test_ethics_school_exam_supported_while_core_subjects_isolated(client, auth, student_auth):
    # 正例：道德与法治（ethics）仅限学校考试归档与列表查询，不进入核心四科练习与画像。
    created = client.post(
        "/api/school-exams",
        json={
            "subject": "ethics",
            "title": "虚构测试数据：九年级十月道法练习",
            "exam_date": "2026-10-15",
            "earned_points": 0,
            "max_points": 50,
            "confirmed_by_user": False,
        },
        headers=auth,
    )
    assert created.status_code == 201
    assert created.json()["status"] == "unconfirmed"
    assert created.json()["knowledge_evidence_created"] is False
    exam_id = created.json()["id"]

    listed = client.get("/api/school-exams?subject=ethics", headers=auth)
    assert listed.status_code == 200
    assert len(listed.json()) == 1 and listed.json()[0]["id"] == exam_id
    assert listed.json()[0]["confirmed_by_user"] is False

    # 反例：ethics 不得进入核心四科的练习取题、画像与题源台账。
    assert client.get("/api/practice/next?subject=ethics", headers=student_auth).status_code == 422
    assert client.get("/api/guidance/profile?subject=ethics", headers=student_auth).status_code == 422
    assert client.post("/api/admin/sources", json={"title": "越界题源", "subject": "ethics"}, headers=auth).status_code == 422
    assert "ethics" not in client.get("/api/subjects", headers=student_auth).json()


def test_confirm_pending_school_exam_total_and_immutability(client, auth, student_auth):
    # 正例：待核对校考可通过 /confirm 补充实得总分并锁定，且仍不产生考点证据。
    created = client.post(
        "/api/school-exams",
        json={
            "subject": "math",
            "title": "虚构测试数据：十月月考待补分",
            "exam_date": "2026-10-15",
            "earned_points": 0,
            "max_points": 100,
            "confirmed_by_user": False,
        },
        headers=auth,
    )
    assert created.status_code == 201
    exam_id = created.json()["id"]

    # 反例：未勾选 confirmed_by_user=True 或超满分均被 422 拦截。
    assert (
        client.post(
            f"/api/school-exams/{exam_id}/confirm",
            json={"confirmed_by_user": False, "earned_points": 88},
            headers=auth,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/school-exams/{exam_id}/confirm",
            json={"confirmed_by_user": True, "earned_points": 101},
            headers=auth,
        ).status_code
        == 422
    )
    # 越权：学生令牌不可确认校考总分。
    assert (
        client.post(
            f"/api/school-exams/{exam_id}/confirm",
            json={"confirmed_by_user": True, "earned_points": 88},
            headers=student_auth,
        ).status_code
        == 403
    )

    confirmed = client.post(
        f"/api/school-exams/{exam_id}/confirm",
        json={"confirmed_by_user": True, "earned_points": 88.5},
        headers=auth,
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["confirmed_by_user"] is True
    assert body["earned_points"] == 88.5
    assert body["knowledge_evidence_created"] is False
    assert profile_knowledge(client, student_auth, subject="math") == []

    # 不可变反例：已确认后同分 409 SCHOOL_EXAM_ALREADY_CONFIRMED，异分 409 SCHOOL_EXAM_IMMUTABLE。
    repeat = client.post(
        f"/api/school-exams/{exam_id}/confirm",
        json={"confirmed_by_user": True, "earned_points": 88.5},
        headers=auth,
    )
    assert repeat.status_code == 409 and repeat.json()["detail"] == "SCHOOL_EXAM_ALREADY_CONFIRMED"
    changed = client.post(
        f"/api/school-exams/{exam_id}/confirm",
        json={"confirmed_by_user": True, "earned_points": 90},
        headers=auth,
    )
    assert changed.status_code == 409 and changed.json()["detail"] == "SCHOOL_EXAM_IMMUTABLE"
    assert (
        client.post(
            "/api/school-exams/missing-id/confirm",
            json={"confirmed_by_user": True, "earned_points": 50},
            headers=auth,
        ).status_code
        == 404
    )
