"""ST-015 题池体检：纯函数正反例 + 只读端点契约（全部虚构测试数据）。"""
from shutong.guidance import pool_health


def test_empty_pool_is_honest_zeros():
    r = pool_health([])
    assert r["knowledge"] == []
    assert r["questions_published"] == 0
    assert r["questions_unseen_for_evaluation"] == 0
    assert r["evaluation_available"] is False
    assert r["disclaimer"]  # 空池也必须带免责口径，不得出现推测字段
    assert "score" not in " ".join(r.keys()).lower()


def test_counts_split_seen_and_unseen_per_knowledge():
    entries = [
        {"question_id": "q1", "knowledge_id": "k1", "seen": False},
        {"question_id": "q2", "knowledge_id": "k1", "seen": True},
        {"question_id": "q3", "knowledge_id": "k2", "seen": True},
    ]
    r = pool_health(entries)
    assert [(k["knowledge_id"], k["published"], k["unseen_for_evaluation"], k["exposed"]) for k in r["knowledge"]] == [
        ("k1", 2, 1, 1), ("k2", 1, 0, 1)
    ]
    assert r["questions_published"] == 3
    assert r["questions_unseen_for_evaluation"] == 1
    assert r["evaluation_available"] is True


def test_multi_knowledge_question_counts_once_in_totals():
    entries = [
        {"question_id": "q1", "knowledge_id": "k1", "seen": True},
        {"question_id": "q1", "knowledge_id": "k2", "seen": True},
    ]
    r = pool_health(entries)
    assert r["questions_published"] == 1  # 一题只算一题
    assert r["questions_unseen_for_evaluation"] == 0
    assert [k["published"] for k in r["knowledge"]] == [1, 1]  # 知识点行按行计数


def test_knowledge_rows_sorted_and_stable():
    entries = [
        {"question_id": "q1", "knowledge_id": "kb", "seen": False},
        {"question_id": "q2", "knowledge_id": "ka", "seen": False},
    ]
    r = pool_health(entries)
    assert [k["knowledge_id"] for k in r["knowledge"]] == ["ka", "kb"]
    assert r == pool_health(list(reversed(entries)))  # 纯函数与输入顺序无关


# ---------- 端点契约（隔离内存库；经 admin/practice 真实链路构造状态） ----------

def test_pool_health_endpoint_reflects_exposures(client, auth, student_auth, published):
    # 5 题同属 math.arithmetic（published fixture）；取一题训练 → 该逻辑题曝光一次。
    nxt = client.get("/api/practice/next?subject=math&purpose=training", headers=student_auth)
    assert nxt.status_code == 200
    r = client.get("/api/guidance/pool-health?subject=math", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["subject"] == "math"
    assert body["questions_published"] == 5
    assert body["questions_unseen_for_evaluation"] == 4
    assert body["evaluation_available"] is True
    row = body["knowledge"][0]
    assert row["knowledge_id"] == "math.arithmetic"
    assert (row["published"], row["unseen_for_evaluation"], row["exposed"]) == (5, 4, 1)
    assert body["disclaimer"]


def test_pool_health_endpoint_empty_subject(client, auth, published):
    r = client.get("/api/guidance/pool-health?subject=english", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["knowledge"] == []
    assert body["questions_published"] == 0
    assert body["evaluation_available"] is False


def test_pool_health_requires_owner(client, published):
    assert client.get("/api/guidance/pool-health?subject=math").status_code == 401


def test_pool_health_counts_latest_published_version_once(client, auth):
    # 修订产生新版本：已发布题修改 → 新草稿，不改变“当前发布版”计数口径（仍算 1 题）。
    src = client.post("/api/admin/sources", json={"title": "虚构测试题源", "subject": "math", "rights_status": "personal_use_reviewed", "verified": True}, headers=auth).json()["id"]
    q = client.post("/api/admin/questions", json={"source_document_id": src, "stem": "示例题：1+1=?", "options": ["A. 1", "B. 2"], "correct_answer": "B", "knowledge_ids": ["math.arithmetic"], "max_points": 2}, headers=auth).json()["id"]
    assert client.post(f"/api/admin/questions/{q}/review", headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{q}/publish", headers=auth).status_code == 200
    rev = client.post(f"/api/admin/questions/{q}/revisions", json={"source_document_id": src, "stem": "示例题（更正）：1+1=?？", "options": ["A. 1", "B. 2"], "correct_answer": "B", "knowledge_ids": ["math.arithmetic"], "max_points": 2}, headers=auth)
    assert rev.status_code == 201
    body = client.get("/api/guidance/pool-health?subject=math", headers=auth).json()
    assert body["questions_published"] == 1
    assert body["questions_unseen_for_evaluation"] == 1
