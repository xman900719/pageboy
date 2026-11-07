"""ST-018 会话续答：刷新/重开恢复最近未作答曝光（隔离内存库 + 真实 API 链路）。"""


def test_resume_returns_latest_unanswered_exposure(client, student_auth, published):
    nxt = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth)
    assert nxt.status_code == 200
    exposure_id = nxt.json()["exposure_id"]
    stem = nxt.json()["stem"]

    r = client.get("/api/practice/resume?subject=math", headers=student_auth)
    assert r.status_code == 200
    item = r.json()["item"]
    assert item is not None
    assert item["exposure_id"] == exposure_id  # 同一曝光续答，不新建、不双烧未见题
    assert item["stem"] == stem
    assert item["purpose"] == "evaluation"
    assert item["unseen_at_exposure"] is True


def test_resume_is_null_after_answered(client, student_auth, published):
    nxt = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth).json()
    assert client.post("/api/practice/attempts", json={
        "client_attempt_id": "11111111-1111-1111-1111-111111111111",
        "exposure_id": nxt["exposure_id"], "answer": "B", "hints_used": False,
    }, headers=student_auth).status_code == 201

    r = client.get("/api/practice/resume?subject=math", headers=student_auth).json()
    assert r["item"] is None  # 已作答即无待续会话


def test_resume_is_null_when_never_claimed(client, student_auth, published):
    assert client.get("/api/practice/resume?subject=math", headers=student_auth).json()["item"] is None


def test_resume_requires_owner(client, published):
    assert client.get("/api/practice/resume?subject=math").status_code == 401


def test_resume_filters_by_subject_and_purpose(client, auth, student_auth):
    # math 有未作答**诊断**曝光；english 无任何题 → 不得把 math 的会话泄漏到 english。
    src = client.post("/api/admin/sources", json={"title": "虚构测试题源", "subject": "math", "rights_status": "personal_use_reviewed", "verified": True}, headers=auth).json()["id"]
    q = client.post("/api/admin/questions", json={"source_document_id": src, "stem": "示例题：1+1=?", "options": ["A. 1", "B. 2"], "correct_answer": "B", "knowledge_ids": ["math.arithmetic"], "max_points": 2}, headers=auth).json()["id"]
    assert client.post(f"/api/admin/questions/{q}/review", headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{q}/publish", headers=auth).status_code == 200
    client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth)
    assert client.get("/api/practice/resume?subject=math", headers=student_auth).json()["item"] is not None
    assert client.get("/api/practice/resume?subject=english", headers=student_auth).json()["item"] is None


def test_training_exposure_is_not_resumed(client, student_auth, published):
    # 训练取题无状态成本：未作答训练曝光不进入续答（诊断未见题才是稀缺资源）。
    client.get("/api/practice/next?subject=math&purpose=training", headers=student_auth)
    assert client.get("/api/practice/resume?subject=math", headers=student_auth).json()["item"] is None


def test_resume_returns_most_recent_when_multiple(client, auth, student_auth):
    src = client.post("/api/admin/sources", json={"title": "虚构测试题源", "subject": "math", "rights_status": "personal_use_reviewed", "verified": True}, headers=auth).json()["id"]
    for i in range(2):
        q = client.post("/api/admin/questions", json={"source_document_id": src, "stem": f"示例题 {i}：1+1=?", "options": ["A. 1", "B. 2"], "correct_answer": "B", "knowledge_ids": ["math.arithmetic"], "max_points": 2}, headers=auth).json()["id"]
        assert client.post(f"/api/admin/questions/{q}/review", headers=auth).status_code == 200
        assert client.post(f"/api/admin/questions/{q}/publish", headers=auth).status_code == 200
    first = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth).json()
    second = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=student_auth).json()
    assert first["stem"] != second["stem"]
    resumed = client.get("/api/practice/resume?subject=math", headers=student_auth).json()["item"]
    assert resumed["exposure_id"] == second["exposure_id"]  # 最近一次未作答诊断曝光
