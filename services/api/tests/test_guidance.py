from shutong.guidance import (
    Evidence,
    summarize,
    make_plan,
    compare_validation,
    analyze_school_exam_errors,
    MIN_DISTINCT_ITEMS,
)

def evidence(id, correct=True, independent=True, first=True):
    return Evidence(source_event_id=id, question_version_id=id, knowledge_id="k", earned_points=1 if correct else 0, max_points=1, independent=independent, is_first_exposure=first)

def test_missing_is_not_zero():
    assert summarize([]) == []
    p = make_plan([], 90, 100, 15, ["k"])
    assert p["steps"][0]["gap_type"] == "INSUFFICIENT_EVIDENCE"
    assert p["target_mapping_status"] == "heuristic_not_calibrated"

def test_only_first_independent_counted():
    data=[evidence("a"), evidence("b",False), evidence("c"), evidence("d",False,False), evidence("e",True,True,False)]
    r=summarize(data)
    assert len(r) == 1 and r[0]["sample_size"] == MIN_DISTINCT_ITEMS
    assert abs(r[0]["observed_rate"] - 2/3) < .0001

def test_repeat_does_not_inflate_evidence():
    e=evidence("a")
    assert summarize([e,e])[0]["sample_size"] == 1


# ---- ST-005 增补：compare_validation 边界（全部虚构测试数据；实现落地前为红） ----

def val_evidence(id, knowledge_id="k", correct=True, independent=True, first=True, max_points=1.0):
    # 复用本文件既有 evidence() 助手形态，局部扩展 knowledge_id（不改动上方既有助手）。
    return Evidence(source_event_id=id, question_version_id=id, knowledge_id=knowledge_id, earned_points=max_points if correct else 0.0, max_points=max_points, independent=independent, is_first_exposure=first)

def test_validation_empty_is_cannot_compare():
    r = compare_validation([], [])
    assert r["verdict"] == "CANNOT_COMPARE"
    assert r["comparable"] is False
    assert r["score_prediction"] is None
    assert r["knowledge"] == []

def test_validation_insufficient_retest_side():
    baseline = [val_evidence(f"b{i}") for i in range(3)]
    retest = [val_evidence("r0")]
    r = compare_validation(baseline, retest)
    entry = r["knowledge"][0]
    assert entry["knowledge_id"] == "k"
    assert entry["verdict"] == "cannot_compare"
    assert entry["reason"] == "insufficient_retest"
    assert r["verdict"] == "CANNOT_COMPARE"
    assert r["comparable"] is False
    assert r["score_prediction"] is None

def test_validation_insufficient_baseline_side():
    baseline = [val_evidence("b0")]
    retest = [val_evidence(f"r{i}") for i in range(3)]
    r = compare_validation(baseline, retest)
    entry = r["knowledge"][0]
    assert entry["knowledge_id"] == "k"
    assert entry["verdict"] == "cannot_compare"
    assert entry["reason"] == "insufficient_baseline"
    assert r["verdict"] == "CANNOT_COMPARE"
    assert r["comparable"] is False

def test_validation_improved_on_comparable_scope():
    baseline = [val_evidence(f"b{i}", correct=False) for i in range(3)]  # 观察率 0
    retest = [val_evidence(f"r{i}") for i in range(3)]  # 观察率 1
    r = compare_validation(baseline, retest)
    assert r["verdict"] == "IMPROVED_ON_COMPARABLE_SCOPE"
    assert r["comparable"] is True
    assert r["score_prediction"] is None
    assert r["disclaimer"]  # 小样本对比必须有免责声明，且不得是涨分宣称
    entry = r["knowledge"][0]
    assert entry["knowledge_id"] == "k"
    assert entry["verdict"] == "improved"
    assert entry["baseline_rate"] == 0 and entry["retest_rate"] == 1
    assert entry["baseline_items"] == 3 and entry["retest_items"] == 3

def test_validation_no_improvement_not_overstated():
    baseline = [val_evidence(f"b{i}") for i in range(3)]
    retest = [val_evidence(f"r{i}") for i in range(3)]  # 两侧观察率相等
    r = compare_validation(baseline, retest)
    assert r["knowledge"][0]["verdict"] == "no_improvement"  # 相等不得宣称 improved
    assert r["verdict"] == "NO_OBSERVED_IMPROVEMENT"
    assert r["comparable"] is True
    assert r["score_prediction"] is None

def test_validation_filters_non_independent_and_repeats():
    baseline_k = [
        val_evidence("b0", correct=False), val_evidence("b1", correct=False), val_evidence("b2", correct=False),
        val_evidence("b2", correct=False),  # 同 question_version_id 重复提交：去重，不得膨胀样本
        val_evidence("hinted", correct=True, independent=False),  # 带提示作答：非独立，必须过滤
        val_evidence("zero", correct=False, max_points=0),  # max_points<=0：与 summarize 同纪律过滤
    ]
    retest_k = [
        val_evidence("r0"), val_evidence("r1"), val_evidence("r2"),
        val_evidence("r1"),  # 重复条目：去重后 retest_items 仍为 3
    ]
    baseline_only = [val_evidence(f"o{i}", knowledge_id="k.only") for i in range(3)]  # 仅一侧存在且够量
    r = compare_validation(baseline_k + baseline_only, retest_k)
    by_id = {e["knowledge_id"]: e for e in r["knowledge"]}
    assert set(by_id) == {"k", "k.only"}
    entry = by_id["k"]
    assert entry["verdict"] == "improved"
    assert entry["baseline_items"] == 3 and entry["retest_items"] == 3
    assert entry["baseline_rate"] == 0 and entry["retest_rate"] == 1  # 混入提示/重复条目会改变观察率
    only = by_id["k.only"]
    assert only["verdict"] == "cannot_compare"  # 单侧样本充足仍不可比
    assert only["reason"] == "insufficient_retest"
    assert r["comparable"] is True

def test_validation_mixed_knowledge_scopes():
    gap_base = [val_evidence(f"gb{i}", knowledge_id="k.gap", correct=False) for i in range(3)]
    gap_retest = [val_evidence(f"gr{i}", knowledge_id="k.gap") for i in range(3)]
    thin_base = [val_evidence(f"tb{i}", knowledge_id="k.thin") for i in range(3)]
    thin_retest = [val_evidence("tr0", knowledge_id="k.thin")]
    r = compare_validation(gap_base + thin_base, gap_retest + thin_retest)
    assert r["comparable"] is True
    assert r["verdict"] == "IMPROVED_ON_COMPARABLE_SCOPE"  # 总判决只由可比范围决定
    assert [e["knowledge_id"] for e in r["knowledge"]] == ["k.gap", "k.thin"]  # knowledge 按 id 排序
    assert r["knowledge"][0]["verdict"] == "improved"
    thin = r["knowledge"][1]
    assert thin["verdict"] == "cannot_compare"
    assert thin["reason"] == "insufficient_retest"


# ---- 学校考试错误分析与跨场次对比纯函数测试（全部虚构测试数据） ----

def _exam_meta(exam_id="ex-cur", subject="math", title="虚构测试数据：十月月考", exam_date="2026-10-15",
               earned_points=82.0, max_points=100.0, confirmed_by_user=True):
    return {
        "id": exam_id,
        "subject": subject,
        "title": title,
        "exam_date": exam_date,
        "earned_points": earned_points,
        "max_points": max_points,
        "confirmed_by_user": confirmed_by_user,
    }


def _school_item(item_id, label, knowledge_id, earned, max_pts, confirmed=True,
                 error_category=None, error_note=None, knowledge_name=None):
    return {
        "id": item_id,
        "question_label": label,
        "knowledge_id": knowledge_id,
        "knowledge_name": knowledge_name or knowledge_id,
        "earned_points": earned,
        "max_points": max_pts,
        "scoring_origin": "manual_entry" if confirmed else "ocr_draft",
        "confirmed_by_user": confirmed,
        "error_category": error_category,
        "error_note": error_note,
    }


def test_school_error_analysis_totals_only_and_unconfirmed_drafts():
    # 反例 1：仅录总分无逐题明细 -> insufficient_items，绝不凭空推算考点
    r = analyze_school_exam_errors(_exam_meta(earned_points=85.0), [], [])
    assert r["status"] == "insufficient_items"
    assert r["overview"]["paper_lost_points"] == 15.0
    assert r["overview"]["unaccounted_lost_points"] == 15.0
    assert r["by_category"] == []
    assert r["by_knowledge"] == []

    # 反例 2：未确认总分的归档场次，不虚构 paper_lost_points；仅有未确认 OCR 草稿亦不进正式统计
    drafts = [_school_item("d1", "第1题", "math.geom", 1.0, 4.0, confirmed=False, error_category="concept")]
    r_draft = analyze_school_exam_errors(
        _exam_meta(earned_points=0.0, confirmed_by_user=False),
        drafts,
        [],
    )
    assert r_draft["status"] == "insufficient_items"
    assert r_draft["overview"]["paper_lost_points"] is None
    assert r_draft["overview"]["unconfirmed_draft_count"] == 1
    assert r_draft["by_knowledge"] == []


def test_school_error_analysis_full_score_items_and_partial_gap():
    items = [_school_item("i1", "第1题", "math.ok", 3.0, 3.0, knowledge_name="达标考点")]
    r = analyze_school_exam_errors(_exam_meta(earned_points=90.0), items, [])
    assert r["status"] == "no_errors_recorded"
    assert r["overview"]["itemized_lost_points"] == 0.0
    assert r["overview"]["unaccounted_lost_points"] == 10.0
    assert "仍有 10 分失分尚未拆解" in r["diagnosis_summary"]


def test_school_error_analysis_single_cross_and_recurring():
    current_items = [
        _school_item("c1", "第5题", "math.eq", 3.0, 3.0, knowledge_name="一元二次方程"),
        _school_item("c2", "第18题", "math.eq", 1.0, 5.0, error_category="concept", error_note="判别式漏讨论 a=0", knowledge_name="一元二次方程"),
        _school_item("c3", "第19题", "math.calc", 2.0, 4.0, error_category="calculation", error_note="符号抄错", knowledge_name="实数混合运算"),
        _school_item("c4", "第22题", "math.geo", 3.0, 8.0, error_category=None, error_note="", knowledge_name="圆的切线证明"),
        _school_item("c5", "第23题", "math.draft", 0.0, 6.0, confirmed=False, error_category="method"),
    ]
    history = [
        {
            "exam_id": "ex-past-1",
            "title": "虚构测试数据：九月测验",
            "exam_date": "2026-09-20",
            "items": [
                _school_item("p1", "第10题", "math.eq", 2.0, 4.0, error_category="method", knowledge_name="一元二次方程"),
                _school_item("p2", "第12题", "math.old", 1.0, 3.0, error_category="reading", knowledge_name="一次函数图像"),
            ],
        },
        {
            "exam_id": "ex-past-2",
            "title": "虚构测试数据：期前摸底",
            "exam_date": "2026-09-01",
            "items": [
                _school_item("p3", "第15题", "math.old", 0.0, 4.0, error_category="reading", knowledge_name="一次函数图像"),
            ],
        },
    ]
    practice_mastery = [
        {"code": "math_cand.eq.quadratic", "mastery_status": "weak", "observed_rate": 0.45, "sample_size": 4},
        {"code": "math.calc", "mastery_status": "mastered", "observed_rate": 0.9, "sample_size": 5},
    ]
    r = analyze_school_exam_errors(
        _exam_meta(earned_points=82.0, max_points=100.0),
        current_items,
        history,
        practice_mastery=practice_mastery,
        has_taxonomy=True,
        knowledge_alias_map={"math.eq": ["math_cand.eq.quadratic"]},
    )
    assert r["status"] == "analyzed"
    ov = r["overview"]
    assert ov["confirmed_item_count"] == 4
    assert ov["lost_item_count"] == 3
    assert ov["unconfirmed_draft_count"] == 1
    assert ov["itemized_lost_points"] == 11.0  # 4 + 2 + 5
    assert ov["paper_lost_points"] == 18.0
    assert ov["unaccounted_lost_points"] == 7.0
    assert ov["categorized_item_count"] == 2
    assert ov["uncategorized_item_count"] == 1
    assert ov["primary_error_category"] == "concept"
    assert ov["primary_knowledge_id"] == "math.geo"

    # 错因分布：第22题未归类失5分、concept失4分、calculation失2分
    cats = {c["category"]: c for c in r["by_category"]}
    assert cats["uncategorized"]["lost_points"] == 5.0
    assert cats["concept"]["lost_points"] == 4.0
    assert cats["calculation"]["lost_points"] == 2.0

    # 知识点交叉诊断
    by_kid = {k["knowledge_id"]: k for k in r["by_knowledge"]}
    assert set(by_kid) == {"math.geo", "math.eq", "math.calc"}
    assert by_kid["math.eq"]["item_count"] == 2  # 含第5题满分3/3与第18题1/5
    assert by_kid["math.eq"]["lost_item_count"] == 1
    assert by_kid["math.eq"]["exam_observed_rate"] == 0.5  # (3+1)/(3+5)
    assert by_kid["math.eq"]["diagnosis_tag"] == "double_weak"
    assert by_kid["math.calc"]["diagnosis_tag"] == "exam_slip"
    assert by_kid["math.geo"]["diagnosis_tag"] == "blind_spot"

    # 同科历次顽固失分点（>=2场）：math.eq (ex-cur + ex-past-1, 本场再犯), math.old (ex-past-1 + ex-past-2, 非本场)
    assert [rk["knowledge_id"] for rk in r["recurring_knowledge"]] == ["math.eq", "math.old"]
    assert r["recurring_knowledge"][0]["repeat_in_current_exam"] is True
    assert r["recurring_knowledge"][0]["total_lost_points"] == 6.0
    assert r["recurring_knowledge"][1]["repeat_in_current_exam"] is False


def test_school_error_analysis_ethics_no_taxonomy():
    items = [
        _school_item("e1", "第21题", "法治与社会责任", 3.0, 6.0, error_category="reading", error_note="材料关键词遗漏", knowledge_name="法治与社会责任")
    ]
    r = analyze_school_exam_errors(
        _exam_meta(subject="ethics", earned_points=43.0, max_points=50.0),
        items,
        [],
        practice_mastery=[],
        has_taxonomy=False,
    )
    assert r["status"] == "analyzed"
    assert r["has_taxonomy"] is False
    assert r["by_knowledge"][0]["diagnosis_tag"] == "archive_review"
    assert r["by_knowledge"][0]["practice_status"] == "not_applicable"
