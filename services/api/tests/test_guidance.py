from shutong.guidance import Evidence, summarize, make_plan, compare_validation, MIN_DISTINCT_ITEMS

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
