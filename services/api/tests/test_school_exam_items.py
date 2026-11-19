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


def test_school_exam_error_analysis_workflow_and_guardrails(client, auth, student_auth, published):
    # 反例 1：仅有总分的考试，错误分析必须如实返回 insufficient_items，绝不从总分反推错因。
    cur_id = make_exam(client, auth, title="虚构测试数据：十月数学月考", exam_date="2026-10-15", earned_points=80, max_points=100)
    empty_res = client.get(f"/api/school-exams/{cur_id}/error-analysis", headers=auth)
    assert empty_res.status_code == 200
    assert empty_res.json()["status"] == "insufficient_items"
    assert empty_res.json()["overview"]["paper_lost_points"] == 20.0

    # 权界：学生令牌禁止读取或修改校考错误分析。
    assert client.get(f"/api/school-exams/{cur_id}/error-analysis", headers=student_auth).status_code == 403

    # 先造 3 条日常练习错误作答，令 math.gap（来自 published fixture 或已知考点）呈现薄弱或已达标对照
    for i in range(3):
        served = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth)
        assert served.status_code == 200
        exp = served.json()["exposure_id"]
        # 全部选错（answer='C' 非 'B'）制造日常薄弱/待诊断对照样本
        recorded = client.post(
            "/api/practice/attempts",
            json={"client_attempt_id": f"err-ana-{i}", "exposure_id": exp, "answer": "C"},
            headers=student_auth,
        )
        assert recorded.status_code == 201

    # 录入 1 条满分题（即使传了 error_category 也会自动清空）、1 条失分题（暂未填错因）、1 条未确认 OCR 草稿
    posted = post_items(
        client,
        auth,
        cur_id,
        [
            {"question_label": "第1题", "knowledge_id": "math.ok", "earned_points": 3.0, "max_points": 3.0,
             "scoring_origin": "manual_entry", "error_category": "calculation", "error_note": "满分校验"},
            {"question_label": "第18题", "knowledge_id": "math.arithmetic", "earned_points": 2.0, "max_points": 6.0,
             "scoring_origin": "manual_entry"},
            {"question_label": "第22题", "knowledge_id": "math.geometry", "earned_points": 1.0, "max_points": 8.0,
             "scoring_origin": "ocr_draft", "error_category": "method"},
        ],
    )
    assert posted.status_code == 201
    created_items = {it["question_label"]: it for it in posted.json()["items"]}
    assert created_items["第1题"]["error_category"] is None
    full_item_id = created_items["第1题"]["id"]
    lost_item_id = created_items["第18题"]["id"]

    # 反例 2：对满分题事后标注 error_category 必须返回 422
    assert (
        client.post(
            f"/api/school-exams/{cur_id}/items/{full_item_id}/analysis",
            json={"error_category": "concept"},
            headers=auth,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/school-exams/{cur_id}/items/{lost_item_id}/analysis",
            json={"error_category": "invalid_cat"},
            headers=auth,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/school-exams/{cur_id}/items/{lost_item_id}/analysis",
            json={"error_category": "reading", "error_note": "越权尝试"},
            headers=student_auth,
        ).status_code
        == 403
    )

    # 正例：补充失分题错因分类与复盘备注，得分保持不可变（INV-04）
    updated = client.post(
        f"/api/school-exams/{cur_id}/items/{lost_item_id}/analysis",
        json={"error_category": "reading", "error_note": "漏看条件 x>0"},
        headers=auth,
    )
    assert updated.status_code == 200
    assert updated.json()["error_category"] == "reading"
    assert updated.json()["error_note"] == "漏看条件 x>0"
    assert updated.json()["earned_points"] == 2.0

    # 创建同科历史场次并录入相同知识点失分，检验跨场次顽固失分点对比
    past_id = make_exam(client, auth, title="虚构测试数据：九月诊断测", exam_date="2026-09-18", earned_points=86, max_points=100)
    assert (
        post_items(
            client,
            auth,
            past_id,
            [
                {"question_label": "第10题", "knowledge_id": "math.arithmetic", "earned_points": 1.0, "max_points": 4.0,
                 "scoring_origin": "manual_entry", "error_category": "calculation", "error_note": "九月同类计算错"}
            ],
        ).status_code
        == 201
    )

    ana = client.get(f"/api/school-exams/{cur_id}/error-analysis", headers=auth)
    assert ana.status_code == 200
    body = ana.json()
    assert body["status"] == "analyzed"
    assert body["overview"]["confirmed_item_count"] == 2
    assert body["overview"]["lost_item_count"] == 1
    assert body["overview"]["unconfirmed_draft_count"] == 1  # 第22题未确认草稿不得进正式统计
    assert body["overview"]["itemized_lost_points"] == 4.0
    assert body["overview"]["unaccounted_lost_points"] == 16.0
    assert body["overview"]["primary_error_category"] == "reading"
    assert body["by_category"][0]["category"] == "reading"
    assert body["by_knowledge"][0]["knowledge_id"] == "math.arithmetic"
    assert body["by_knowledge"][0]["knowledge_name"] == "基础算术运算"
    assert body["by_knowledge"][0]["diagnosis_tag"] == "double_weak"
    assert body["history_summary"]["same_subject_exams_with_items"] == 2
    assert body["history_summary"]["recurring_count"] == 1
    assert body["recurring_knowledge"][0]["knowledge_id"] == "math.arithmetic"
    assert body["recurring_knowledge"][0]["repeat_in_current_exam"] is True
    assert body["recurring_knowledge"][0]["total_lost_points"] == 7.0


def test_ethics_school_exam_error_analysis_without_taxonomy(client, auth):
    ethics_id = make_exam(client, auth, subject="ethics", title="虚构测试数据：十月道法", exam_date="2026-10-15", earned_points=42, max_points=50)
    assert (
        post_items(
            client,
            auth,
            ethics_id,
            [
                {"question_label": "第16题", "knowledge_id": "依法治国与宪法权威", "earned_points": 4.0, "max_points": 8.0,
                 "scoring_origin": "manual_entry", "error_category": "norm", "error_note": "缺少材料结合分析"}
            ],
        ).status_code
        == 201
    )
    res = client.get(f"/api/school-exams/{ethics_id}/error-analysis", headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert body["has_taxonomy"] is False
    assert body["status"] == "analyzed"
    assert body["by_knowledge"][0]["knowledge_name"] == "依法治国与宪法权威"
    assert body["by_knowledge"][0]["diagnosis_tag"] == "archive_review"
    assert body["by_knowledge"][0]["practice_status"] == "not_applicable"


def _make_text_layer_pdf(lines: list[str]) -> bytes:
    """生成带可机读文本层的虚构多行测试 PDF。"""
    commands = ["BT", "/F1 14 Tf", "40 740 Td"]
    for idx, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx > 0:
            commands.append("0 -24 Td")
        commands.append(f"({escaped}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [5 0 R] >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{idx} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii")
    data += b"".join(f"{off:010} 00000 n \n".encode("ascii") for off in offsets[1:])
    return data + f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")


def _make_png_bytes() -> bytes:
    """生成最小合法测试 PNG。"""
    from io import BytesIO
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(im)
    draw.rectangle([(10, 10), (390, 60)], fill="black")
    draw.text((20, 120), "Q2 (-2)", fill="black")
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_parse_drafts_skeleton_vision_guardrails_and_discard(client, auth, student_auth, published, tmp_path, monkeypatch):
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    exam_id = make_exam(client, auth, title="虚构测试数据：十月自动草稿测试", earned_points=82, max_points=100)
    pdf_data = _make_text_layer_pdf(
        [
            "1. Compute quadratic equation roots (3 points)",
            "2. Prove triangle congruence in circle (5 points)",
        ]
    )
    png_data = _make_png_bytes()
    att_pdf = client.post(
        f"/api/school-exams/{exam_id}/paper?filename=paper.pdf",
        content=pdf_data,
        headers={**auth, "content-type": "application/pdf"},
    )
    assert att_pdf.status_code == 201
    att_pdf_id = att_pdf.json()["id"]

    att_png = client.post(
        f"/api/school-exams/{exam_id}/paper?filename=answer_card.png",
        content=png_data,
        headers={**auth, "content-type": "image/png"},
    )
    assert att_png.status_code == 201
    att_png_id = att_png.json()["id"]

    # 权界：学生令牌不得调用解析、批量确认、丢弃或外部同步接口
    assert client.post(f"/api/school-exams/{exam_id}/parse-drafts", json={"attachment_ids": [att_pdf_id]}, headers=student_auth).status_code == 403
    assert client.post(f"/api/school-exams/{exam_id}/sync-drafts", json={"items": [{"question_label": "第1题", "earned_points": 2, "max_points": 2}]}, headers=student_auth).status_code == 403
    assert client.post(f"/api/school-exams/{exam_id}/items/confirm-batch", json={"items": [{"item_id": "x", "confirmed_by_human": True, "earned_points": 1}]}, headers=student_auth).status_code == 403

    # 反例：纯图片走 skeleton_only 返回 422；无密钥走 auto 含图片必须 503 fail-closed
    assert (
        client.post(
            f"/api/school-exams/{exam_id}/parse-drafts",
            json={"attachment_ids": [att_png_id], "mode": "skeleton_only"},
            headers=auth,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/school-exams/{exam_id}/parse-drafts",
            json={"attachment_ids": [att_png_id], "mode": "auto"},
            headers=auth,
        ).status_code
        == 503
    )

    # 正例 1：纯文字卷仅本地提取骨架，生成未确认草稿且零证据入画像
    skel = client.post(
        f"/api/school-exams/{exam_id}/parse-drafts",
        json={"attachment_ids": [att_pdf_id], "mode": "skeleton_only"},
        headers=auth,
    )
    assert skel.status_code == 200
    skel_body = skel.json()
    assert skel_body["parser_mode_used"] == "local_text_skeleton"
    assert skel_body["evidence_created"] == 0
    assert [i["question_label"] for i in skel_body["created_items"]] == ["第1题", "第2题"]
    assert all(i["scoring_origin"] == "ocr_draft" and i["confirmed_by_user"] is False for i in skel_body["created_items"])
    assert profile_knowledge(client, student_auth) == []

    q1_id = skel_body["created_items"][0]["id"]
    q2_id = skel_body["created_items"][1]["id"]

    # 正例 2：丢弃未确认第2题草稿；升级版 confirm 一次性核准第1题分值、满分、考点与错因
    assert client.post(f"/api/school-exams/{exam_id}/items/{q2_id}/discard", headers=auth).status_code == 200
    assert (
        client.post(f"/api/school-exams/{exam_id}/items/{q2_id}/discard", headers=student_auth).status_code
        == 403
    )

    confirmed_q1 = client.post(
        f"/api/school-exams/{exam_id}/items/{q1_id}/confirm",
        json={
            "confirmed_by_human": True,
            "earned_points": 1.5,
            "max_points": 3.0,
            "knowledge_id": "math.arithmetic",
            "error_category": "calculation",
            "error_note": "移项未变号",
        },
        headers=auth,
    )
    assert confirmed_q1.status_code == 200
    assert confirmed_q1.json()["confirmed_by_user"] is True
    assert confirmed_q1.json()["max_points"] == 3.0
    assert confirmed_q1.json()["error_category"] == "calculation"
    assert profile_knowledge(client, student_auth)[0]["sample_size"] == 1

    # 反例：已确认题目禁止再被丢弃
    assert client.post(f"/api/school-exams/{exam_id}/items/{q1_id}/discard", headers=auth).status_code == 409

    # 正例 3：配置密钥（Mock）走 DeepSeek 视觉联合解析，自动跳过已确认第1题
    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test-vision")
    import json as _json
    import httpx as _httpx

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": _json.dumps(
                                {
                                    "items": [
                                        {
                                            "question_label": "第1题",
                                            "max_points": 3,
                                            "draft_earned_points": 3,
                                            "knowledge_id": "math.arithmetic",
                                            "confidence": "high",
                                            "reason": "已确认题目应被跳过",
                                        },
                                        {
                                            "question_label": "第2题",
                                            "max_points": 4,
                                            "draft_earned_points": 2,
                                            "knowledge_id": "math.geometry",
                                            "error_category": "method",
                                            "error_note": "缺少辅助线",
                                            "confidence": "medium",
                                            "reason": "左缘批改 -2",
                                        },
                                        {
                                            "question_label": "第3题",
                                            "max_points": 4,
                                            "draft_earned_points": 4,
                                            "knowledge_id": "math.arithmetic",
                                            "confidence": "high",
                                            "reason": "解答完整",
                                        },
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

    real_post = _httpx.Client.post

    def _selective_fake_post(self, url, *args, **kwargs):
        if "chat/completions" in str(url):
            return _FakeResp()
        return real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(_httpx.Client, "post", _selective_fake_post)
    vis = client.post(
        f"/api/school-exams/{exam_id}/parse-drafts",
        json={"attachment_ids": [att_pdf_id, att_png_id], "mode": "auto", "mask_student_header": True},
        headers=auth,
    )
    assert vis.status_code == 200
    vis_body = vis.json()
    assert vis_body["parser_mode_used"].startswith("deepseek_vision:")
    assert vis_body["meta"]["pages_sent"] >= 2
    assert vis_body["meta"]["masked_pages"] == 1
    assert vis_body["skipped_labels"] == ["第1题"]
    assert [i["question_label"] for i in vis_body["created_items"]] == ["第2题", "第3题"]

    vis_q2_id = vis_body["created_items"][0]["id"]
    vis_q3_id = vis_body["created_items"][1]["id"]

    # 原子性反例：批量确认含已确认项第1题 -> 整批 409 回滚，第2/3题保持未确认
    bad_batch = client.post(
        f"/api/school-exams/{exam_id}/items/confirm-batch",
        json={
            "items": [
                {"item_id": vis_q2_id, "confirmed_by_human": True, "earned_points": 2.0},
                {"item_id": q1_id, "confirmed_by_human": True, "earned_points": 1.5},
            ]
        },
        headers=auth,
    )
    assert bad_batch.status_code == 409
    detail_before = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    by_lbl = {it["question_label"]: it for it in detail_before["items"]}
    assert by_lbl["第2题"]["confirmed_by_user"] is False

    # 批量确认正例
    good_batch = client.post(
        f"/api/school-exams/{exam_id}/items/confirm-batch",
        json={
            "items": [
                {
                    "item_id": vis_q2_id,
                    "confirmed_by_human": True,
                    "earned_points": 2.0,
                    "error_category": "method",
                    "error_note": "人工复核确认辅助线思路断档",
                },
                {"item_id": vis_q3_id, "confirmed_by_human": True, "earned_points": 4.0},
            ]
        },
        headers=auth,
    )
    assert good_batch.status_code == 200
    assert good_batch.json()["evidence_created"] == 2
    ana = client.get(f"/api/school-exams/{exam_id}/error-analysis", headers=auth).json()
    assert ana["overview"]["confirmed_item_count"] == 3
    assert ana["overview"]["unconfirmed_draft_count"] == 0


def test_sync_drafts_enrichment_and_replace_guardrails(client, auth, student_auth, published, monkeypatch):
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    exam_id = make_exam(client, auth, title="虚构测试数据：校考平台抓取同步", earned_points=85, max_points=100)
    assert post_items(client, auth, exam_id, [item("第1题", earned_points=3.0, max_points=3.0)]).status_code == 201

    synced = client.post(
        f"/api/school-exams/{exam_id}/sync-drafts",
        json={
            "source_name": "k12100",
            "use_ai": False,
            "items": [
                {"question_label": "第1题", "earned_points": 1.0, "max_points": 3.0},
                {"question_label": "4", "earned_points": 1.0, "max_points": 4.0, "stem_text": "实数运算求解", "wrong_reason": "符号看错"},
                {"question_label": "第5题", "earned_points": 4.0, "max_points": 4.0, "stem_text": "基础几何推理"},
            ],
        },
        headers=auth,
    )
    assert synced.status_code == 200
    body = synced.json()
    assert body["parser_mode_used"] == "external_local_rules"
    assert body["evidence_created"] == 0
    assert body["skipped_labels"] == ["第1题"]  # 已确认第1题绝不被外部同步覆盖
    assert [it["question_label"] for it in body["created_items"]] == ["第4题", "第5题"]
    assert body["created_items"][0]["draft_confidence"] == "external_sync"
    assert body["created_items"][0]["confirmed_by_user"] is False

    # 覆盖重同步时仅更新未确认第4题草稿，第1题仍跳过受保护
    resynced = client.post(
        f"/api/school-exams/{exam_id}/sync-drafts",
        json={
            "source_name": "k12100",
            "use_ai": False,
            "replace_unconfirmed_drafts": True,
            "items": [
                {"question_label": "第1题", "earned_points": 0.0, "max_points": 3.0},
                {"question_label": "4", "earned_points": 2.0, "max_points": 4.0, "stem_text": "实数运算求解"},
            ],
        },
        headers=auth,
    )
    assert resynced.status_code == 200
    assert resynced.json()["skipped_labels"] == ["第1题"]
    assert resynced.json()["created_items"][0]["earned_points"] == 2.0


def test_school_exam_items_natural_order_in_detail_and_analysis(client, auth):
    exam_id = make_exam(client, auth, title="虚构测试数据：题号自然排序校验", earned_points=80, max_points=100)
    resp = post_items(
        client,
        auth,
        exam_id,
        [
            item("10", earned_points=1.0, max_points=2.0),
            item("1", earned_points=2.0, max_points=2.0),
            item("第2题", earned_points=0.0, max_points=2.0),
            item("18(2)", earned_points=2.0, max_points=4.0),
            item("18(1)", earned_points=3.0, max_points=3.0),
        ],
    )
    assert resp.status_code == 201

    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth)
    assert detail.status_code == 200
    assert [it["question_label"] for it in detail.json()["items"]] == [
        "1",
        "第2题",
        "10",
        "18(1)",
        "18(2)",
    ]

    ana = client.get(f"/api/school-exams/{exam_id}/error-analysis", headers=auth)
    assert ana.status_code == 200
    assert ana.json()["by_category"][0]["question_labels"] == [
        "第2题",
        "10",
        "18(2)",
    ]


def test_school_exam_auto_associate_preserves_confirmed_and_existing_items(client, auth):
    exam_id = make_exam(client, auth, subject="math", title="虚构测试数据：自动关联端点保护测试", earned_points=60, max_points=100)
    resp = post_items(
        client,
        auth,
        exam_id,
        [
            item("第1题", knowledge_id="math_cand.num.rational", earned_points=2.0, max_points=2.0),
            item("第2题", knowledge_id="math_cand.alg.poly", earned_points=1.0, max_points=2.0),
            item("第10题", knowledge_id="unmapped", earned_points=0.0, max_points=2.0),
        ],
    )
    assert resp.status_code == 201

    from shutong.database import get_db
    from shutong.main import app
    from shutong import models as m
    from sqlalchemy import select

    session = next(app.dependency_overrides[get_db]())
    try:
        rows = {
            r.question_label: r
            for r in session.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam_id)).scalars().all()
        }
        rows["第1题"].confirmed_by_user = True
        rows["第1题"].scoring_origin = "manual_entry"
        rows["第2题"].confirmed_by_user = False
        rows["第2题"].scoring_origin = "ocr_draft"
        rows["第10题"].confirmed_by_user = False
        rows["第10题"].scoring_origin = "ocr_draft"
        rows["第10题"].draft_reason = "分析报告册第13页；题型=填空题"
        session.commit()
    finally:
        session.close()

    res = client.post(
        f"/api/school-exams/{exam_id}/items/auto-associate",
        json={"use_ai": False, "overwrite_existing": False},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["skipped_confirmed"] == 1
    assert summary["updated"] == 2

    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    by_lbl = {it["question_label"]: it for it in detail["items"]}
    # 已确认第 1 题绝不被改写
    assert by_lbl["第1题"]["confirmed_by_user"] is True
    assert by_lbl["第1题"]["knowledge_id"] == "math_cand.num.rational"
    # 未确认但已有知识点的第 2 题保持既有 knowledge_id，仅补全 3 个候选
    assert by_lbl["第2题"]["confirmed_by_user"] is False
    assert by_lbl["第2题"]["knowledge_id"] == "math_cand.alg.poly"
    assert len(by_lbl["第2题"]["draft_knowledge_candidates"]) == 3
    # 原 unmapped 第 10 题被自动关联且保持未确认
    assert by_lbl["第10题"]["confirmed_by_user"] is False
    assert by_lbl["第10题"]["knowledge_id"] not in {"", "unmapped"}
    assert len(by_lbl["第10题"]["draft_knowledge_candidates"]) == 3


def test_student_reflection_workflow_anti_perfunctory_and_admin_return(client, auth, student_auth, monkeypatch):
    """学生端完成错因与双栏防敷衍复盘，管理端只读查看并支持退回重写。"""
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    exam_id = make_exam(client, auth, subject="math", title="虚构测试数据：学生端错题复盘闭环", earned_points=88, max_points=100)
    resp = post_items(
        client,
        auth,
        exam_id,
        [
            item("第1题", knowledge_id="math_cand.num.rational", earned_points=2.0, max_points=2.0),
            item("第8题", knowledge_id="math_cand.eq.fractional", earned_points=0.0, max_points=3.0),
        ],
    )
    assert resp.status_code == 201

    # 学生端仅看到已确认的失分题第 8 题，且响应严禁包含内部 knowledge_id
    list_res = client.get("/api/student/school-exam-reflections?subject=math", headers=student_auth)
    assert list_res.status_code == 200, list_res.text
    list_body = list_res.json()
    assert list_body["total_pending"] == 1
    assert list_body["pending_counts_by_subject"]["math"] == 1
    assert len(list_body["items"]) == 1
    lost_item = list_body["items"][0]
    assert lost_item["question_label"] == "第8题"
    assert lost_item["reflection_status"] == "pending"
    assert "knowledge_id" not in lost_item
    assert "math_cand" not in lost_item["topic"]

    # 敷衍填写被 422 拦截
    bad_res = client.post(
        f"/api/student/school-exam-reflections/{lost_item['item_id']}",
        json={
            "error_category": "reading",
            "stuck_point": "太粗心了没看清",
            "fix_strategy": "下次一定注意认真审题",
        },
        headers=student_auth,
    )
    assert bad_res.status_code == 422
    assert "REFLECTION_TOO_PERFUNCTORY" in bad_res.json()["detail"]

    # 仅点句式起头不补全具体内容，同样被 422 拦截
    starter_only_res = client.post(
        f"/api/student/school-exam-reflections/{lost_item['item_id']}",
        json={
            "error_category": "reading",
            "stuck_point": "题目里的「」条件我没用上，当时以为",
            "fix_strategy": "如果再看到「」，我就先「」。",
        },
        headers=student_auth,
    )
    assert starter_only_res.status_code == 422
    assert "REFLECTION_TOO_PERFUNCTORY" in starter_only_res.json()["detail"]

    # 具体实质复盘提交成功
    ok_res = client.post(
        f"/api/student/school-exam-reflections/{lost_item['item_id']}",
        json={
            "error_category": "method",
            "stuck_point": "去分母乘以最简公分母后忘记检验增根 x=2 导致多选",
            "fix_strategy": "解分式方程得出根后必须立即代回原方程各分母验证不为零",
        },
        headers=student_auth,
    )
    assert ok_res.status_code == 200, ok_res.text
    assert ok_res.json()["reflection_status"] == "completed"
    assert ok_res.json()["error_category"] == "method"

    # 管理端只读详情可见结构化复盘字段
    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    q8 = next(it for it in detail["items"] if it["question_label"] == "第8题")
    assert q8["reflection_status"] == "completed"
    assert "增根" in q8["stuck_point"]

    # 管理端退回重写后重回学生端待复盘队列
    ret_res = client.post(
        f"/api/school-exams/{exam_id}/items/{lost_item['item_id']}/return-reflection",
        json={"reason": "请补充说明验根的具体代入过程"},
        headers=auth,
    )
    assert ret_res.status_code == 200, ret_res.text
    assert ret_res.json()["reflection_status"] == "needs_revision"
    assert ret_res.json()["return_reason"] == "请补充说明验根的具体代入过程"

    list_after = client.get("/api/student/school-exam-reflections?subject=math", headers=student_auth).json()
    assert list_after["total_pending"] == 1
    assert list_after["items"][0]["reflection_status"] == "needs_revision"
    assert list_after["items"][0]["return_reason"] == "请补充说明验根的具体代入过程"
    assert "增根" in list_after["items"][0]["stuck_point"]


def test_auto_associate_upgrades_type_inferred_when_paper_attached(client, auth, monkeypatch) -> None:
    """报告生成的 type_inferred 草稿在上传原卷后，不传 overwrite 也应自动升级为 AI/关键词匹配结果，且不覆盖已确认项。"""
    exam_id = make_exam(client, auth, title="虚构测试数据：先验升级测试", earned_points=88)

    # 插入一条未确认的 type_inferred 草稿与一条已确认项
    seeded = post_items(
        client,
        auth,
        exam_id,
        [
            {
                "question_label": "第1题",
                "knowledge_id": "math.number_sense",
                "earned_points": 2.0,
                "max_points": 3.0,
                "scoring_origin": "ocr_draft",
                "draft_confidence": "low",
                "draft_knowledge_candidates": [
                    {"knowledge_id": "math.number_sense", "title": "数感", "reason": "题型先验"},
                    {"knowledge_id": "math.arithmetic", "title": "运算", "reason": "题型先验"},
                    {"knowledge_id": "math.equations", "title": "方程", "reason": "题型先验"},
                ],
            },
            {
                "question_label": "第2题",
                "knowledge_id": "math.number_sense",
                "earned_points": 3.0,
                "max_points": 3.0,
                "scoring_origin": "manual_entry",
                "draft_confidence": "low",
            },
        ],
    )
    assert seeded.status_code == 201, seeded.text

    from sqlalchemy import select
    from shutong import models as m
    from shutong.main import app, get_db

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        for row in db.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam_id)).scalars():
            row.draft_confidence = "type_inferred"
        db.commit()
    finally:
        db_gen.close()

    # 上传一份含第1、2题题干的 docx 原卷
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>1. 解一元二次方程 x^2 - 5x + 6 = 0。</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>2. 计算 (-2) + 3 的值。</w:t></w:r></w:p>"
            "</w:body></w:document>",
        )
    up = client.post(
        f"/api/school-exams/{exam_id}/paper",
        params={"filename": "paper.docx"},
        content=buf.getvalue(),
        headers={
            **auth,
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    )
    assert up.status_code == 201, up.text

    from shutong import school_paper_parser as parser

    called: list[bool] = []

    def fake_auto_associate(*, subject, knowledge_catalog, items, use_ai=True):
        called.append(use_ai)
        return [
            {
                "knowledge_id": "math.equations",
                "draft_knowledge_candidates": [
                    {"knowledge_id": "math.equations", "title": "方程与不等式", "reason": "AI 语义匹配"},
                    {"knowledge_id": "math.arithmetic", "title": "数与式运算", "reason": "次选"},
                    {"knowledge_id": "math.functions", "title": "函数", "reason": "备选"},
                ],
                "draft_confidence": "ai_recommended",
                "method": "ai_recommended",
                "basis_note": "AI 语义匹配",
            }
            for _ in items
        ]

    monkeypatch.setattr(parser, "auto_associate_school_items", fake_auto_associate)

    res = client.post(
        f"/api/school-exams/{exam_id}/items/auto-associate",
        json={"use_ai": True, "overwrite_existing": False},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 1
    assert res.json()["skipped_confirmed"] == 1
    assert called == [True]

    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    by_label = {it["question_label"]: it for it in detail["items"]}
    assert by_label["第1题"]["knowledge_id"] == "math.equations"
    assert by_label["第1题"]["draft_confidence"] == "ai_recommended"
    assert by_label["第2题"]["knowledge_id"] == "math.number_sense"


def _upload_dummy_png_attachment(client, auth, exam_id: str, filename: str = "虚构测试数据-原卷.png") -> None:
    from PIL import Image
    from io import BytesIO

    buf = BytesIO()
    Image.new("RGB", (120, 120), color=(255, 255, 255)).save(buf, format="PNG")
    res = client.post(
        f"/api/school-exams/{exam_id}/paper",
        params={"filename": filename},
        content=buf.getvalue(),
        headers={**auth, "Content-Type": "image/png"},
    )
    assert res.status_code == 201, res.text


def test_extract_stems_never_repeats_and_isolates_unconfirmed(client, auth, student_auth, monkeypatch):
    """ST-022：逐题仅 AI 解析一次、未确认不进学生端、失败释放认领、确认后永不覆盖。"""
    from datetime import timedelta
    from shutong import database, models as m, school_paper_parser as parser

    exam_id = make_exam(client, auth, subject="math", title="虚构测试数据：题干防重复解析", earned_points=90, max_points=100)
    post_items(
        client,
        auth,
        exam_id,
        [
            item("第1题", knowledge_id="math_cand.num.rational", earned_points=2.0, max_points=2.0),
            item("第8题", knowledge_id="math_cand.eq.fractional", earned_points=1.0, max_points=4.0),
            item("第9题", knowledge_id="math_cand.eq.fractional", earned_points=0.0, max_points=4.0),
        ],
    )
    _upload_dummy_png_attachment(client, auth, exam_id)

    # 无 Key 时纯图片返回 503 且不锁定题目状态
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    no_key_res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=auth)
    assert no_key_res.status_code == 503

    # 学生无权调用管理端抽取/确认接口
    assert client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=student_auth).status_code == 403

    # 配置测试 Key 并模拟上游先失败一次（应释放认领以便重试）
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-dummy")
    calls: list[list[str]] = []

    def fail_then_ok(*, subject, attachments, lost_labels, cfg):
        calls.append(list(lost_labels))
        if len(calls) == 1:
            raise parser.VisionParserUnavailableError("VISION_PARSER_TIMEOUT")
        return {
            "第8题": {"stem_text": "解方程 $\\frac{1}{x-2}=1$", "student_answer_text": "x=3"},
            # 第9题故意未返回，验证标为 not_found 后不再重复请求
        }

    monkeypatch.setattr(parser, "extract_lost_item_stems_with_deepseek", fail_then_ok)

    fail_res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=auth)
    assert fail_res.status_code == 503
    assert len(calls) == 1

    # 重试成功：仅第8题与第9题进入提示词，满分第1题绝不参与
    ok_res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=auth)
    assert ok_res.status_code == 200, ok_res.text
    body = ok_res.json()
    assert body == {
        "requested": 2,
        "embedded": 0,
        "vision": 1,
        "not_found": 1,
        "remaining_unextracted": 0,
        "ai_called": True,
        "ai_unavailable_reason": None,
    }
    assert sorted(calls[1]) == ["第8题", "第9题"]

    # 第二次调用抽取：所有失分题已有状态（vision_draft / not_found），绝不重复调用 AI
    second_res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=auth)
    assert second_res.status_code == 200
    assert second_res.json()["requested"] == 0
    assert second_res.json()["ai_called"] is False
    assert len(calls) == 2

    # 未确认前，学生端看不到任何题干与作答
    stu_before = client.get("/api/student/school-exam-reflections?subject=math", headers=student_auth).json()
    q8_stu_before = next(x for x in stu_before["items"] if x["question_label"] == "第8题")
    assert q8_stu_before["stem_excerpt"] is None
    assert q8_stu_before["student_answer_excerpt"] is None

    # 满分题不可手工设置题干
    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    by_lbl = {it["question_label"]: it for it in detail["items"]}
    assert by_lbl["第1题"]["stem_state"] is None
    assert by_lbl["第8题"]["stem_state"] == "vision_draft"
    assert by_lbl["第9题"]["stem_state"] == "not_found"
    full_patch = client.patch(
        f"/api/school-exams/{exam_id}/items/{by_lbl['第1题']['id']}/stem",
        json={"stem_text": "不应允许", "confirm": True},
        headers=auth,
    )
    assert full_patch.status_code == 422

    # 家长批量确认第8题草稿，并检查分数与知识点未被修改
    confirm_res = client.post(f"/api/school-exams/{exam_id}/confirm-stems", headers=auth)
    assert confirm_res.status_code == 200
    assert confirm_res.json()["confirmed_count"] == 1

    detail_after = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    q8_after = next(it for it in detail_after["items"] if it["question_label"] == "第8题")
    assert q8_after["stem_state"] == "confirmed"
    assert q8_after["earned_points"] == 1.0
    assert q8_after["max_points"] == 4.0
    assert q8_after["knowledge_id"] == "math_cand.eq.fractional"

    # 确认后学生端可见已确认题干与作答
    stu_after = client.get("/api/student/school-exam-reflections?subject=math", headers=student_auth).json()
    q8_stu_after = next(x for x in stu_after["items"] if x["question_label"] == "第8题")
    assert q8_stu_after["stem_excerpt"] == "解方程 $\\frac{1}{x-2}=1$"
    assert q8_stu_after["student_answer_excerpt"] == "x=3"

    # 再次调用抽取仍不重复解析且不覆盖已确认内容
    third_res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=auth)
    assert third_res.json()["ai_called"] is False
    assert len(calls) == 2

    # 模拟第9题处于未超时的 extracting 认领中时不会并发重入；超过 10 分钟 TTL 才允许认领
    from shutong.database import get_db
    from shutong.main import app

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        row9 = db.get(m.SchoolExamItem, by_lbl["第9题"]["id"])
        row9.stem_state = "extracting"
        row9.stem_state_at = m.now()
        db.commit()
    finally:
        db.close()

    concurrent_res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=auth)
    assert concurrent_res.json()["ai_called"] is False

    db_gen2 = app.dependency_overrides[get_db]()
    db2 = next(db_gen2)
    try:
        row9 = db2.get(m.SchoolExamItem, by_lbl["第9题"]["id"])
        row9.stem_state_at = m.now() - timedelta(minutes=11)
        db2.commit()
    finally:
        db2.close()

    stale_res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={}, headers=auth)
    assert stale_res.status_code == 200
    assert stale_res.json()["ai_called"] is True
    assert calls[-1] == ["第9题"]


def test_extract_lost_item_stems_filters_whitelist_and_answer_leaks(monkeypatch):
    """ST-022：白名单之外的题号与含参考答案字样的条目必须被丢弃。"""
    from PIL import Image
    from io import BytesIO
    from shutong import school_paper_parser as parser

    buf = BytesIO()
    Image.new("RGB", (80, 80), color=(255, 255, 255)).save(buf, format="PNG")
    monkeypatch.setattr(
        parser,
        "_post_deepseek_json",
        lambda cfg, *, model, messages, max_tokens=8192, timeout_override=None: {
            "stems": [
                {"question_label": "第1题", "stem": "不在失分白名单里", "student_answer": "A"},
                {"question_label": "第8题", "stem": "求 x 的值。参考答案：x=2", "student_answer": "x=1"},
                {"question_label": "9", "stem": "已知三角形面积为 6，求高。", "student_answer": ""},
            ]
        },
    )
    cfg = parser.VisionParserConfig(
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        vision_model="deepseek-flash",
        text_model="deepseek-chat",
        timeout_seconds=30.0,
    )
    out = parser.extract_lost_item_stems_with_deepseek(
        subject="math",
        attachments=[{"id": "a1", "filename": "p.png", "media_type": "image/png", "data": buf.getvalue()}],
        lost_labels=["第8题", "第9题"],
        cfg=cfg,
    )
    assert list(out.keys()) == ["第9题"]
    assert out["第9题"]["stem_text"] == "已知三角形面积为 6，求高。"
    assert out["第9题"]["student_answer_text"] is None


def test_extract_stems_batched_persists_partial_and_compresses_jpeg(client, auth, monkeypatch):
    """分批抽取每批立即落库；后批失败绝不丢失前批结果，且视觉帧启用 JPEG 压缩。"""
    from PIL import Image
    from io import BytesIO
    import base64
    from shutong import school_paper_parser as parser

    buf = BytesIO()
    Image.new("RGB", (2400, 1200), color=(255, 255, 255)).save(buf, format="PNG")
    frames = parser.render_masked_pages_for_vision(
        [{"id": "a1", "filename": "卷.png", "media_type": "image/png", "data": buf.getvalue()}],
        compress_jpeg=True,
        max_edge=1600,
    )
    assert len(frames) == 1
    assert frames[0]["data_url"].startswith("data:image/jpeg;base64,")
    raw_jpg = base64.b64decode(frames[0]["data_url"].split(",", 1)[1])
    with Image.open(BytesIO(raw_jpg)) as resized:
        assert max(resized.size) <= 1600

    exam_id = make_exam(client, auth, subject="math", title="虚构测试数据：分批抽取测试", earned_points=90, max_points=100)
    post_items(
        client,
        auth,
        exam_id,
        [
            item("8", knowledge_id="math_cand.eq.fractional", earned_points=0.0, max_points=3.0),
            item("15", knowledge_id="math_cand.eq.fractional", earned_points=0.0, max_points=3.0),
        ],
    )
    _upload_dummy_png_attachment(client, auth, exam_id)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-dummy")

    batch_calls: list[list[str]] = []

    def batch_fake(*, subject, attachments, lost_labels, cfg):
        batch_calls.append(list(lost_labels))
        if len(batch_calls) == 2:
            raise parser.VisionParserUnavailableError("VISION_PARSER_TIMEOUT")
        return {
            "8": {"stem_text": "求二次函数最小值", "student_answer_text": "y=1"},
        }

    monkeypatch.setattr(parser, "extract_lost_item_stems_with_deepseek", batch_fake)

    r1 = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={"batch_size": 1}, headers=auth)
    assert r1.status_code == 200, r1.text
    assert r1.json()["requested"] == 1
    assert r1.json()["vision"] == 1
    assert r1.json()["remaining_unextracted"] == 1

    # 第 2 批超时失败（503），但第 1 批结果必须已经持久化
    r2 = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={"batch_size": 1}, headers=auth)
    assert r2.status_code == 503

    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth).json()
    by_lbl = {it["question_label"]: it for it in detail["items"]}
    assert by_lbl["8"]["stem_state"] == "vision_draft"
    assert by_lbl["15"]["stem_state"] is None

    # 重试仅认领第 15 题，绝不重复解析第 8 题
    r3 = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={"batch_size": 1}, headers=auth)
    assert r3.status_code == 200
    assert r3.json()["remaining_unextracted"] == 0
    assert batch_calls == [["8"], ["15"], ["15"]]


def test_parse_model_json_content_handles_fences_and_latex_escapes():
    """JSON 容错解析：剥离代码块围栏并修复未双写的 LaTeX 反斜杠，非法文本仍拒绝。"""
    import pytest
    from shutong import school_paper_parser as parser

    fenced = '好的，以下是结果：\n```json\n{"stems": [{"question_label": "8", "stem": "$\\sqrt{x} + \\angle A = 0$"}]}\n```'
    parsed = parser.parse_model_json_content(fenced)
    assert parsed["stems"][0]["question_label"] == "8"
    assert "\\sqrt{x}" in parsed["stems"][0]["stem"]

    # 单反斜杠未转义（模型直接输出 \sqrt / \angle）
    single_slash = '{"stems": [{"question_label": "8", "stem": "$\\sqrt{x} + ' + r'\angle A + \cdot' + '$"}]}'
    parsed2 = parser.parse_model_json_content(single_slash)
    assert "\\angle A" in parsed2["stems"][0]["stem"]

    with pytest.raises(ValueError):
        parser.parse_model_json_content("抱歉，无法识别")


def test_post_deepseek_json_reports_truncated_when_finish_reason_length(monkeypatch):
    """finish_reason=length 且输出为空时，必须明确抛出 VISION_PARSER_TRUNCATED。"""
    import pytest
    from shutong import school_paper_parser as parser

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "", "reasoning_content": "..."},
                    }
                ]
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr(parser, "_open_httpx_client", lambda *a, **kw: FakeClient())
    cfg = parser.VisionParserConfig("https://api.deepseek.com", "sk-t", "deepseek-flash", "deepseek-chat", 30.0)
    with pytest.raises(parser.VisionParserUnavailableError, match="VISION_PARSER_TRUNCATED"):
        parser._post_deepseek_json(cfg, model=cfg.vision_model, messages=[{"role": "user", "content": "hi"}])


def test_extract_stems_releases_claim_even_with_expire_on_commit_false(client, auth, monkeypatch):
    """即使 Session 使用 expire_on_commit=False，503 释放认领也必须真正把数据库恢复为 None，绝不卡死在 extracting。"""
    from sqlalchemy.orm import sessionmaker
    from shutong import database, models as m, school_paper_parser as parser
    from shutong.main import app

    exam_id = make_exam(client, auth, subject="math", title="虚构测试数据：expire_on_commit释放", earned_points=90, max_points=100)
    post_items(
        client,
        auth,
        exam_id,
        [item("8", knowledge_id="math_cand.eq.fractional", earned_points=0.0, max_points=3.0)],
    )
    _upload_dummy_png_attachment(client, auth, exam_id)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-dummy")
    monkeypatch.setattr(
        parser,
        "extract_lost_item_stems_with_deepseek",
        lambda **kwargs: (_ for _ in ()).throw(parser.VisionParserUnavailableError("VISION_PARSER_TRUNCATED")),
    )

    # 验证与生产 SessionLocal 一致的 expire_on_commit=False 行为
    db_gen = app.dependency_overrides[database.get_db]()
    test_db = next(db_gen)
    bind = test_db.get_bind()
    test_db.close()
    NoExpireSession = sessionmaker(bind=bind, expire_on_commit=False)

    def override_no_expire():
        with NoExpireSession() as s:
            yield s

    prev = app.dependency_overrides[database.get_db]
    app.dependency_overrides[database.get_db] = override_no_expire
    try:
        res = client.post(f"/api/school-exams/{exam_id}/extract-stems", json={"batch_size": 2}, headers=auth)
        assert res.status_code == 503
        assert res.json()["detail"] == "VISION_PARSER_TRUNCATED"

        with NoExpireSession() as s:
            row = s.query(m.SchoolExamItem).filter_by(school_exam_id=exam_id).one()
            assert row.stem_state is None
            assert row.stem_source is None
    finally:
        app.dependency_overrides[database.get_db] = prev



