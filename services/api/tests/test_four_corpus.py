"""四科语料增量：来源隔离、知识点版本化与双向关联、勘误不可变、覆盖缺口、回测时间边界。"""
from __future__ import annotations
from shutong.research import backtest, predict, statistics, coverage_report


def mk_source(client, auth, **kw):
    body = {"title": "虚构测试数据-北京市中考", "subject": "math", "exam_year": 2025, "rights_status": "personal_use_reviewed", "verified": True, "source_class": "official_exam"}
    body.update(kw)
    return client.post("/api/admin/sources", json=body, headers=auth)


def mk_question(client, auth, src, stem="虚构测试数据：1+1=?"):
    r = client.post("/api/admin/questions", json={"source_document_id": src, "stem": stem, "options": ["A. 1", "B. 2"], "correct_answer": "B", "knowledge_ids": ["math.x"], "max_points": 1}, headers=auth)
    assert r.status_code == 201
    return r.json()["id"]


def test_district_and_third_party_rejected_but_other_classes_allowed(client, auth):
    assert mk_source(client, auth, title="2023年海淀区中考一模").json()["detail"] == "DISTRICT_PAPER_REJECTED"
    assert mk_source(client, auth, title="2019北京中考数学逐题解析").json()["detail"] == "THIRD_PARTY_ANALYSIS_NOT_OFFICIAL"
    assert mk_source(client, auth, title="海淀区教辅练习", source_class="aux_book").status_code == 201


def test_non_four_subject_rejected(client, auth):
    assert mk_source(client, auth, subject="chemistry").status_code == 422


def test_knowledge_versioning_keeps_history_and_bidirectional(client, auth):
    src = mk_source(client, auth).json()["id"]
    qv = mk_question(client, auth, src)
    node = client.post("/api/admin/knowledge/nodes", json={"subject": "math", "code": "math.alg.1", "name": "一次方程"}, headers=auth).json()
    link = client.post("/api/admin/knowledge/links", json={"question_version_id": qv, "node_id": node["id"], "role": "core", "evidence": "题干含一次方程"}, headers=auth).json()
    assert link["node_version"] == 1
    assert client.post(f"/api/admin/knowledge/nodes/{node['id']}/versions", json={"name": "一元一次方程"}, headers=auth).json()["version"] == 2
    forward = client.get(f"/api/admin/questions/{qv}/knowledge", headers=auth).json()
    assert forward[0]["node_version"] == 1  # 历史关联仍指向当时版本
    backward = client.get(f"/api/admin/knowledge/nodes/{node['id']}/questions", headers=auth).json()
    assert backward[0]["question_version_id"] == qv
    assert client.post("/api/admin/knowledge/links", json={"question_version_id": qv, "node_id": node["id"]}, headers=auth).status_code == 409
    assert client.post(f"/api/admin/knowledge/nodes/{node['id']}/deprecate", headers=auth).json()["status"] == "deprecated"
    assert client.get(f"/api/admin/questions/{qv}/knowledge", headers=auth).json()[0]["node_version"] == 1


def test_link_subject_mismatch_rejected(client, auth):
    qv = mk_question(client, auth, mk_source(client, auth).json()["id"])
    node = client.post("/api/admin/knowledge/nodes", json={"subject": "physics", "code": "phy.1", "name": "运动"}, headers=auth).json()
    assert client.post("/api/admin/knowledge/links", json={"question_version_id": qv, "node_id": node["id"]}, headers=auth).status_code == 422


def test_erratum_does_not_change_original(client, auth, ):
    from shutong.database import get_db
    from shutong.main import app
    qv = mk_question(client, auth, mk_source(client, auth).json()["id"], stem="原始题干")
    assert client.post(f"/api/admin/questions/{qv}/errata", json={"note": "选项B排版有误"}, headers=auth).status_code == 201
    db = next(app.dependency_overrides[get_db]())
    from shutong import models as m
    assert db.get(m.QuestionVersion, qv).stem == "原始题干"


def test_coverage_detects_missing_and_separates_statuses(client, auth):
    src = mk_source(client, auth).json()["id"]
    qv = mk_question(client, auth, src)
    cov = client.get("/api/admin/coverage?year_from=2024&year_to=2025", headers=auth).json()
    status = {(c["year"], c["subject"]): c["status"] for c in cov["cells"]}
    assert status[(2024, "math")] == "missing"
    assert status[(2025, "math")] == "recorded"  # 有来源但未采录完成/未审核，不等于已审核
    client.post(f"/api/admin/sources/{src}/status", json={"ingest_status": "ingested"}, headers=auth)
    client.post(f"/api/admin/sources/{src}/status", json={"review_status": "approved"}, headers=auth)
    cov = client.get("/api/admin/coverage?year_from=2025&year_to=2025", headers=auth).json()
    assert {(c["year"], c["subject"]): c["status"] for c in cov["cells"]}[(2025, "math")] == "ingested"  # 草稿题不能被误判为 reviewed
    assert client.post(f"/api/admin/questions/{qv}/review", headers=auth).status_code == 200
    cov = client.get("/api/admin/coverage?year_from=2025&year_to=2025", headers=auth).json()
    assert {(c["year"], c["subject"]): c["status"] for c in cov["cells"]}[(2025, "math")] == "ingested"  # reviewed 尚未发布
    assert client.post(f"/api/admin/questions/{qv}/publish", headers=auth).status_code == 200
    cov = client.get("/api/admin/coverage?year_from=2025&year_to=2025", headers=auth).json()
    assert {(c["year"], c["subject"]): c["status"] for c in cov["cells"]}[(2025, "math")] == "reviewed"


def test_coverage_excludes_aux_sources(client, auth):
    mk_source(client, auth, source_class="aux_book", title="虚构教辅")
    cov = client.get("/api/admin/coverage?year_from=2025&year_to=2025", headers=auth).json()
    assert all(c["status"] == "missing" for c in cov["cells"])


ROWS = [{"year": y, "kind": "single_choice", "knowledge": ["k.a", "k.b"] if y < 2022 else ["k.a", "k.c"]} for y in (2019, 2020, 2021, 2022)]


def test_prediction_never_uses_future_data():
    base = predict(ROWS, 2021)
    polluted = predict(ROWS + [{"year": 2030, "kind": "x", "knowledge": ["k.future"] * 50}, {"year": 2021, "kind": "x", "knowledge": ["k.same_year"]}], 2021)
    assert base == polluted  # 目标年及之后的数据对预测无影响
    assert "k.future" not in str(polluted) and "k.same_year" not in str(polluted)
    assert statistics(ROWS + [{"year": 2025, "kind": "z", "knowledge": []}], 2021)["question_count"] == 2


def test_backtest_insufficient_and_no_invented_rate():
    assert predict(ROWS[:1], 2020)["status"] == "insufficient_evidence"
    bt = backtest(ROWS[:1])
    assert bt["summary"]["hit_rate"] is None
    full = backtest(ROWS)
    assert [r["status"] for r in full["results"]] == ["insufficient_evidence", "insufficient_evidence", "evaluated", "evaluated"]
    assert 0 <= full["summary"]["hit_rate"] <= 1


def test_research_run_marks_ai_blocked_and_official_only(client, auth):
    mk_source(client, auth, source_class="aux_book", title="虚构教辅")
    r = client.post("/api/admin/research/runs", json={"subject": "math", "target_year": 2026}, headers=auth).json()
    assert r["output"]["ai_inference"].startswith("BLOCKED")
    assert r["output"]["statistics"]["question_count"] == 0
    assert r["output"]["prediction"]["status"] == "insufficient_evidence"
    assert client.get("/api/admin/research/runs", headers=auth).json()[0]["id"] == r["id"]


def test_coverage_versions_count_once_and_draft_does_not_replace_published(client, auth, monkeypatch):
    from shutong import fourcorpus

    src = mk_source(client, auth).json()["id"]
    qv = mk_question(client, auth, src)
    assert client.post(f"/api/admin/sources/{src}/status", json={"ingest_status": "ingested"}, headers=auth).status_code == 200
    assert client.post(f"/api/admin/sources/{src}/status", json={"review_status": "approved"}, headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{qv}/review", headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{qv}/publish", headers=auth).status_code == 200
    revision = client.post(
        f"/api/admin/questions/{qv}/revisions",
        json={"source_document_id": src, "stem": "修订草稿", "options": ["A. 1", "B. 2"],
              "correct_answer": "B", "knowledge_ids": ["math.x"], "max_points": 1},
        headers=auth,
    )
    assert revision.status_code == 201
    newer = revision.json()["id"]

    original_report = fourcorpus.coverage_report
    counted = []

    def capture(docs, year_from, year_to):
        counted.extend(d for d in docs if d["id"] == src)
        return original_report(docs, year_from, year_to)

    monkeypatch.setattr(fourcorpus, "coverage_report", capture)
    def check():
        response = client.get("/api/admin/coverage?year_from=2025&year_to=2025", headers=auth)
        assert response.status_code == 200
        assert next(c for c in response.json()["cells"] if c["year"] == 2025 and c["subject"] == "math")["status"] == "reviewed"
        assert counted[-1]["question_count"] == 1
        assert counted[-1]["reviewed_question_count"] == 1

    check()  # 新草稿并不抹掉已经审核发布的旧版
    assert client.post(f"/api/admin/questions/{newer}/review", headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{newer}/publish", headers=auth).status_code == 200
    check()  # 同一逻辑题的两个发布版本也只能各计一次


def test_coverage_report_pure_draft_only_not_reviewed():
    docs = [{"id": "d", "subject": "math", "exam_year": 2025, "sha256": None,
             "ingest_status": "ingested", "verified": True, "review_status": "approved",
             "question_count": 1, "reviewed_question_count": 0}]
    report = coverage_report(docs, 2025, 2025)
    assert next(c for c in report["cells"] if c["subject"] == "math")["status"] == "ingested"
    docs[0]["reviewed_question_count"] = 1
    report = coverage_report(docs, 2025, 2025)
    assert next(c for c in report["cells"] if c["subject"] == "math")["status"] == "reviewed"


def test_research_run_backtest_excludes_target_and_future_years(client, auth, monkeypatch):
    from shutong import fourcorpus

    history = [
        {"year": year, "kind": "single_choice", "knowledge": ["k.a"]}
        for year in (2019, 2020, 2021)
    ]
    later = [
        {"year": 2022, "kind": "fill_blank", "knowledge": ["k.target"]},
        {"year": 2030, "kind": "fill_blank", "knowledge": ["k.future"]},
    ]
    monkeypatch.setattr(fourcorpus, "_official_rows", lambda db, subject: history)
    baseline = client.post("/api/admin/research/runs", json={"subject": "math", "target_year": 2022}, headers=auth)
    assert baseline.status_code == 201

    monkeypatch.setattr(fourcorpus, "_official_rows", lambda db, subject: history + later)
    with_later_data = client.post("/api/admin/research/runs", json={"subject": "math", "target_year": 2022}, headers=auth)
    assert with_later_data.status_code == 201

    # 目标年和未来数据不得改变回测结果，也不得进入统计与预测。
    assert with_later_data.json()["output"] == baseline.json()["output"]
    output = with_later_data.json()["output"]
    assert [r["year"] for r in output["backtest"]["results"]] == [2019, 2020, 2021]
    assert output["backtest"]["summary"]["evaluated_years"] == 1
    assert output["statistics"]["years_used"] == [2019, 2020, 2021]
    assert "k.target" not in str(output) and "k.future" not in str(output)


def test_coverage_report_pure_flags_duplicate_hash():
    docs = [{"id": str(i), "subject": "math", "exam_year": 2025, "sha256": "a" * 64, "ingest_status": "recorded", "verified": False, "review_status": "pending", "question_count": 0} for i in range(2)]
    assert coverage_report(docs, 2025, 2025)["duplicate_sha256"] == ["a" * 64]




def test_coverage_duplicate_hash_ignores_unbacked_legacy_claims(client, auth):
    # 本地离线文件未入库、或旧版来源仅人工填写 SHA256，均不构成已上传原件。
    first = mk_source(client, auth, title='虚构测试数据：来源A').json()['id']
    second = mk_source(client, auth, title='虚构测试数据：来源B').json()['id']
    from shutong.database import get_db
    from shutong.main import app
    from shutong import models as m
    db = next(app.dependency_overrides[get_db]())
    for source_id in (first, second):
        db.get(m.SourceDocument, source_id).sha256 = 'a' * 64
    db.commit()
    db.close()

    report = client.get('/api/admin/coverage?year_from=2025&year_to=2025', headers=auth).json()
    assert report['duplicate_sha256'] == []
    math_cell = next(c for c in report['cells'] if c['subject'] == 'math')
    assert math_cell['status'] == 'recorded'  # 已登记，不代表本地 PDF 不存在或已导入
    missing = next(c for c in report['cells'] if c['subject'] == 'physics')
    assert missing['status'] == 'missing'  # 仅表示数据库无已登记来源


def _research_statistics(client, auth):
    response = client.post("/api/admin/research/runs", json={"subject": "math", "target_year": 2026}, headers=auth)
    assert response.status_code == 201
    return response.json()["output"]["statistics"]


def test_research_requires_approved_source_and_published_question(client, auth):
    src = mk_source(client, auth).json()["id"]
    qv = mk_question(client, auth, src)

    # 即使来源已被标记为已采录，审核前、题目仍为草稿时都不计入研究。
    assert _research_statistics(client, auth)["question_count"] == 0
    assert client.post(f"/api/admin/sources/{src}/status", json={"ingest_status": "ingested"}, headers=auth).status_code == 200
    assert client.post(f"/api/admin/sources/{src}/status", json={"review_status": "approved"}, headers=auth).status_code == 200
    assert _research_statistics(client, auth)["question_count"] == 0

    assert client.post(f"/api/admin/questions/{qv}/review", headers=auth).status_code == 200
    assert _research_statistics(client, auth)["question_count"] == 0
    assert client.post(f"/api/admin/questions/{qv}/publish", headers=auth).status_code == 200
    assert _research_statistics(client, auth)["question_count"] == 1

    # 来源 verified 与 review_status 是独立的门槛，不能只检查后者。
    from shutong import models as m
    from shutong.database import get_db
    from shutong.main import app
    db = next(app.dependency_overrides[get_db]())
    source = db.get(m.SourceDocument, src)
    source.verified = False
    db.commit()
    db.close()
    assert _research_statistics(client, auth)["question_count"] == 0


def test_research_uses_latest_published_version_and_approved_links(client, auth):
    src = mk_source(client, auth).json()["id"]
    assert client.post(f"/api/admin/sources/{src}/status", json={"ingest_status": "ingested"}, headers=auth).status_code == 200
    assert client.post(f"/api/admin/sources/{src}/status", json={"review_status": "approved"}, headers=auth).status_code == 200
    original = mk_question(client, auth, src)
    node_resp = client.post("/api/admin/knowledge/nodes", json={"subject": "math", "code": "math.research.test", "name": "测试知识点"}, headers=auth)
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]
    link_resp = client.post("/api/admin/knowledge/links", json={"question_version_id": original, "node_id": node_id}, headers=auth)
    assert link_resp.status_code == 201
    link_id = link_resp.json()["id"]
    assert client.post(f"/api/admin/questions/{original}/review", headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{original}/publish", headers=auth).status_code == 200

    # 未审核的关联不得贡献知识点频次，但发布题仍计入题量。
    assert _research_statistics(client, auth)["question_count"] == 1
    assert _research_statistics(client, auth)["knowledge_frequency"] == {}
    assert client.post(f"/api/admin/knowledge/links/{link_id}/review", headers=auth).status_code == 200
    assert _research_statistics(client, auth)["knowledge_frequency"] == {"math.research.test": 1}

    revision = client.post(
        f"/api/admin/questions/{original}/revisions",
        json={"source_document_id": src, "stem": "修订版（草稿）", "options": ["A. 1", "B. 2"],
              "correct_answer": "B", "knowledge_ids": ["math.x"], "max_points": 1},
        headers=auth,
    )
    assert revision.status_code == 201
    revised_id = revision.json()["id"]

    # 较新的草稿不能替代当前已发布版；新旧版本不能重复计数。
    stats = _research_statistics(client, auth)
    assert stats["question_count"] == 1
    assert stats["knowledge_frequency"] == {"math.research.test": 1}

    assert client.post(f"/api/admin/questions/{revised_id}/review", headers=auth).status_code == 200
    assert client.post(f"/api/admin/questions/{revised_id}/publish", headers=auth).status_code == 200
    stats = _research_statistics(client, auth)
    assert stats["question_count"] == 1
    assert stats["knowledge_frequency"] == {}  # 旧版审核关联不得自动继承给新版
