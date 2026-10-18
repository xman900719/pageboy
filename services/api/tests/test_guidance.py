from shutong.guidance import Evidence, summarize, make_plan, MIN_DISTINCT_ITEMS

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
