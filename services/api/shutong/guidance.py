"""Pure domain functions. No HTTP, SQLAlchemy, OCR, AI SDK or file I/O here."""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from typing import Literal

MODEL_VERSION = "guidance-heuristic-v0.1-unvalidated"
MIN_DISTINCT_ITEMS = 3

@dataclass(frozen=True)
class Evidence:
    source_event_id: str
    question_version_id: str
    knowledge_id: str
    earned_points: float
    max_points: float
    independent: bool
    is_first_exposure: bool


def summarize(evidence: list[Evidence]) -> list[dict]:
    """Use only first, independent, scored, single-knowledge item evidence.

    Missing evidence is UNKNOWN, never zero. Deduplicate versions to avoid inflating samples.
    """
    grouped: dict[str, dict[str, Evidence]] = defaultdict(dict)
    for item in evidence:
        if not item.independent or not item.is_first_exposure or item.max_points <= 0:
            continue
        grouped[item.knowledge_id].setdefault(item.question_version_id, item)
    out = []
    for kid, versions in sorted(grouped.items()):
        vals = list(versions.values())
        rate = sum(x.earned_points for x in vals) / sum(x.max_points for x in vals)
        out.append({"knowledge_id": kid, "sample_size": len(vals), "observed_rate": round(rate, 4), "evidence_status": "sufficient_for_heuristic" if len(vals) >= MIN_DISTINCT_ITEMS else "insufficient_evidence"})
    return out


def provisional_threshold(target_points: float, max_points: float) -> float:
    """UNVALIDATED planning proxy, not an exam score equivalence or prediction."""
    ratio = target_points / max_points
    return 0.7 if ratio <= 0.7 else (0.8 if ratio <= 0.85 else 0.9)


def _validation_groups(evidence: list[Evidence]) -> dict[str, dict[str, Evidence]]:
    """Filter by evidence discipline, then group by knowledge and dedup versions (first wins)."""
    grouped: dict[str, dict[str, Evidence]] = defaultdict(dict)
    for item in evidence:
        if not item.independent or not item.is_first_exposure or item.max_points <= 0:
            continue
        grouped[item.knowledge_id].setdefault(item.question_version_id, item)
    return grouped


def compare_validation(baseline: list[Evidence], retest: list[Evidence]) -> dict:
    """Observable first-vs-retest comparison; never claims score gains on incomparable scope."""
    baseline_groups = _validation_groups(baseline)
    retest_groups = _validation_groups(retest)
    knowledge = []
    comparable_kids = []
    for kid in sorted(set(baseline_groups) | set(retest_groups)):
        b_items = list(baseline_groups.get(kid, {}).values())
        r_items = list(retest_groups.get(kid, {}).values())
        if len(b_items) >= MIN_DISTINCT_ITEMS and len(r_items) >= MIN_DISTINCT_ITEMS:
            comparable_kids.append(kid)
            b_rate = sum(x.earned_points for x in b_items) / sum(x.max_points for x in b_items)
            r_rate = sum(x.earned_points for x in r_items) / sum(x.max_points for x in r_items)
            knowledge.append({"knowledge_id": kid, "verdict": "improved" if r_rate > b_rate else "no_improvement",
                              "baseline_rate": round(b_rate, 4), "retest_rate": round(r_rate, 4),
                              "baseline_items": len(b_items), "retest_items": len(r_items)})
        else:
            # 不足原因先查 baseline，再查 retest；两侧都不足时报 insufficient_baseline。
            reason = "insufficient_baseline" if len(b_items) < MIN_DISTINCT_ITEMS else "insufficient_retest"
            knowledge.append({"knowledge_id": kid, "verdict": "cannot_compare", "reason": reason,
                              "baseline_items": len(b_items), "retest_items": len(r_items)})
    if not comparable_kids:
        verdict, comparable = "CANNOT_COMPARE", False
    else:
        b_pooled = sum(x.earned_points for kid in comparable_kids for x in baseline_groups[kid].values()) / sum(x.max_points for kid in comparable_kids for x in baseline_groups[kid].values())
        r_pooled = sum(x.earned_points for kid in comparable_kids for x in retest_groups[kid].values()) / sum(x.max_points for kid in comparable_kids for x in retest_groups[kid].values())
        verdict, comparable = ("IMPROVED_ON_COMPARABLE_SCOPE" if r_pooled > b_pooled else "NO_OBSERVED_IMPROVEMENT"), True
    return {"model_version": MODEL_VERSION, "verdict": verdict, "comparable": comparable, "score_prediction": None,
            "knowledge": knowledge, "disclaimer": "小样本可观察对比；不是中考分数预测、不等值不同考试、不可比范围不宣称涨分。"}


def make_plan(profile: list[dict], target_points: float, max_points: float, minutes_per_day: int, known_knowledge_ids: list[str]) -> dict:
    threshold = provisional_threshold(target_points, max_points)
    by_kid = {item["knowledge_id"]: item for item in profile}
    steps = []
    for kid in sorted(set(known_knowledge_ids)):
        p = by_kid.get(kid)
        if p is None or p["sample_size"] < MIN_DISTINCT_ITEMS:
            steps.append({"knowledge_id": kid, "gap_type": "INSUFFICIENT_EVIDENCE", "action": "diagnostic_unseen_items", "reason": "尚无足够的独立新题证据", "priority": 0})
        elif p["observed_rate"] < threshold:
            steps.append({"knowledge_id": kid, "gap_type": "KNOWLEDGE_GAP", "action": "targeted_practice_then_unseen_evaluation", "reason": "独立得分表现低于未校准规划阈值", "priority": 1, "observed_rate": p["observed_rate"]})
        else:
            steps.append({"knowledge_id": kid, "gap_type": "NO_CONFIRMED_GAP", "action": "spaced_review", "reason": "当前证据未确认短板；仍需跨时间验证", "priority": 2})
    steps.sort(key=lambda x: (x["priority"], x["knowledge_id"]))
    return {"model_version": MODEL_VERSION, "target_mapping_status": "heuristic_not_calibrated", "planning_threshold": threshold, "minutes_per_day": minutes_per_day, "steps": steps, "disclaimer": "不是中考分数预测；学校卷总分不参与考点画像。"}
