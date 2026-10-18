from uuid import uuid4

def test_auth_and_health(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/api/subjects").status_code == 401

def test_unreviewed_or_unknown_source_cannot_publish(client, auth):
    src = client.post("/api/admin/sources", json={"title": "No rights", "subject": "math"}, headers=auth).json()["id"]
    q = client.post("/api/admin/questions", json={"source_document_id": src, "stem": "x=1?", "options": ["A", "B"], "correct_answer": "A", "knowledge_ids": ["k"], "max_points": 1}, headers=auth).json()["id"]
    assert client.post(f"/api/admin/questions/{q}/publish", headers=auth).status_code == 409
    assert client.post(f"/api/admin/questions/{q}/review", headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{q}/publish", headers=auth).status_code == 409
    assert client.get("/api/practice/next?subject=math", headers=auth).status_code == 404

def test_attempt_idempotency_and_unseen_separation(client, auth, published):
    item = client.get("/api/practice/next?subject=math&purpose=training", headers=auth).json()
    assert item["question_version_id"] in published
    body = {"client_attempt_id": "once-1", "exposure_id": item["exposure_id"], "answer": "B"}
    r1 = client.post("/api/practice/attempts", json=body, headers=auth)
    assert r1.status_code == 201 and r1.json()["earned_points"] == 2.0
    r2 = client.post("/api/practice/attempts", json=body, headers=auth)
    assert r2.status_code == 201 and r2.json()["status"] == "already_recorded"
    conflict = client.post("/api/practice/attempts", json={**body, "answer": "A"}, headers=auth)
    assert conflict.status_code == 409
    evaluation = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=auth).json()
    assert evaluation["question_version_id"] != item["question_version_id"]
    assert evaluation["unseen_at_exposure"] is True
    completed = client.post("/api/practice/attempts", json={"client_attempt_id": "evaluation-1", "exposure_id": evaluation["exposure_id"], "answer": "B"}, headers=auth)
    assert completed.status_code == 201 and completed.json()["evaluation_valid_unseen"] is True

def test_school_exam_total_no_knowledge_evidence(client, auth, published):
    r = client.post("/api/school-exams", json={"subject":"math", "title":"周测", "exam_date":"2026-09-18", "earned_points":72, "max_points":100, "confirmed_by_user": True}, headers=auth)
    assert r.status_code == 201 and r.json()["knowledge_evidence_created"] is False
    profile = client.get("/api/guidance/profile?subject=math", headers=auth).json()
    assert profile["knowledge"] == []
    assert profile["score_prediction"] is None

def test_goal_plan_unknown_then_observed(client, auth, published):
    result = client.post("/api/goals", json={"subject":"math", "target_points":90,"max_points":100,"minutes_per_day":15}, headers=auth)
    assert result.status_code == 201
    first = client.get("/api/guidance/plan?subject=math", headers=auth).json()
    assert first["steps"][0]["gap_type"] == "INSUFFICIENT_EVIDENCE"
    # For initial evidence, use five distinct (unseen) question versions.
    for i in range(3):
        ex = client.get("/api/practice/next?subject=math&purpose=evaluation", headers=auth).json()
        r = client.post("/api/practice/attempts", json={"client_attempt_id": f"e-{i}", "exposure_id": ex["exposure_id"], "answer": "A"}, headers=auth)
        assert r.status_code == 201
    profile = client.get("/api/guidance/profile?subject=math", headers=auth).json()
    assert profile["knowledge"][0]["sample_size"] == 3
    assert client.get("/api/guidance/plan?subject=math", headers=auth).json()["steps"][0]["gap_type"] == "KNOWLEDGE_GAP"
