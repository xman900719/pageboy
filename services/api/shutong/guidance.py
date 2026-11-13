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


def pool_health(entries: list[dict]) -> dict:
    """题池体检：只如实计数已发布题与曝光记录；不制造分数、不推断重要性。

    entries: [{"question_id": str, "knowledge_id": str, "seen": bool}]，一题多知识点各计一行；
    题目总数按 question_id 去重（一题只算一题），知识点行按行计数。
    """
    per_kid: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        per_kid[entry["knowledge_id"]].append(entry)
    knowledge = [
        {"knowledge_id": kid, "published": len(rows),
         "unseen_for_evaluation": sum(1 for row in rows if not row["seen"]),
         "exposed": sum(1 for row in rows if row["seen"])}
        for kid, rows in sorted(per_kid.items())
    ]
    questions_published = len({entry["question_id"] for entry in entries})
    questions_unseen = len({entry["question_id"] for entry in entries if not entry["seen"]})
    return {"model_version": MODEL_VERSION, "knowledge": knowledge,
            "questions_published": questions_published, "questions_unseen_for_evaluation": questions_unseen,
            "evaluation_available": questions_unseen > 0,
            "disclaimer": "只计数已发布题目与曝光记录；某知识点题少不等于不重要，可能只是尚未导入。数字不构成分数或能力结论。"}


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


def compute_knowledge_mastery(
    nodes: list[dict],
    evidence: list[Evidence],
    threshold: float = 0.7,
) -> list[dict]:
    """计算已发布非选学知识节点的掌握状态（严格保留证据不足口径，绝不伪造 0 分）。"""
    active_nodes = [n for n in nodes if not n.get("is_elective", False)]
    parent_codes = {n.get("parent_code") for n in active_nodes if n.get("parent_code")}
    grouped = _validation_groups(evidence)

    out: list[dict] = []
    by_code: dict[str, dict] = {}
    for n in active_nodes:
        code = n["code"]
        is_leaf = code not in parent_codes
        vals = list(grouped.get(code, {}).values())
        sample_size = len(vals)
        max_sum = sum(x.max_points for x in vals)
        observed_rate = round(sum(x.earned_points for x in vals) / max_sum, 4) if sample_size > 0 and max_sum > 0 else None

        if sample_size == 0:
            mastery_status = "untested"
        elif sample_size < MIN_DISTINCT_ITEMS:
            mastery_status = "insufficient"
        elif observed_rate is not None and observed_rate >= threshold:
            mastery_status = "mastered"
        else:
            mastery_status = "weak"

        item = {
            "code": code,
            "name": n["name"],
            "domain": n.get("domain"),
            "parent_code": n.get("parent_code"),
            "level": n.get("level", 2),
            "description": n.get("description"),
            "is_leaf": is_leaf,
            "sample_size": sample_size,
            "observed_rate": observed_rate,
            "mastery_status": mastery_status,
        }
        out.append(item)
        by_code[code] = item

    # 对非叶子大类节点，基于其下属非选学子孙叶子聚合统计，方便图谱节点上直观呈现领域掌握度。
    children_map: dict[str, list[str]] = defaultdict(list)
    for n in active_nodes:
        if n.get("parent_code"):
            children_map[n["parent_code"]].append(n["code"])

    def collect_descendant_leaves(root_code: str) -> list[dict]:
        leaves: list[dict] = []
        stack = list(children_map.get(root_code, []))
        visited: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            node_item = by_code.get(cur)
            if node_item is None:
                continue
            if node_item["is_leaf"]:
                leaves.append(node_item)
            else:
                stack.extend(children_map.get(cur, []))
        return leaves

    for item in out:
        if item["is_leaf"]:
            continue
        leaves = collect_descendant_leaves(item["code"])
        tested = [lf for lf in leaves if lf["sample_size"] > 0 and lf["observed_rate"] is not None]
        total_samples = sum(lf["sample_size"] for lf in leaves)
        if tested:
            avg_rate = round(sum(lf["observed_rate"] for lf in tested) / len(tested), 4)
            item["sample_size"] = total_samples
            item["observed_rate"] = avg_rate
            if any(lf["mastery_status"] == "weak" for lf in leaves) and avg_rate < threshold:
                item["mastery_status"] = "weak"
            elif all(lf["mastery_status"] == "mastered" for lf in leaves) and leaves:
                item["mastery_status"] = "mastered"
            elif total_samples >= MIN_DISTINCT_ITEMS and avg_rate >= threshold:
                item["mastery_status"] = "mastered"
            elif total_samples >= MIN_DISTINCT_ITEMS:
                item["mastery_status"] = "weak"
            else:
                item["mastery_status"] = "insufficient"

    return out


def summarize_growth(mastery_items: list[dict], threshold: float = 0.7) -> dict:
    """提炼学生当前优势、薄弱不足、待探索盲区与一级领域维度的成长状态摘要。"""
    leaves = [m for m in mastery_items if m.get("is_leaf", True)]
    strengths = sorted(
        [m for m in leaves if m["mastery_status"] == "mastered"],
        key=lambda x: (-(x["observed_rate"] or 0.0), -x["sample_size"], x["code"]),
    )
    weaknesses = sorted(
        [m for m in leaves if m["mastery_status"] == "weak"],
        key=lambda x: (x["observed_rate"] or 0.0, -x["sample_size"], x["code"]),
    )
    developing = sorted(
        [m for m in leaves if m["mastery_status"] == "insufficient"],
        key=lambda x: (x["observed_rate"] if x["observed_rate"] is not None else 1.0, -x["sample_size"], x["code"]),
    )
    untested = [m for m in leaves if m["mastery_status"] == "untested"]

    # 按一级领域（parent_code 为空）聚合雷达/条形维度统计
    top_domains = [m for m in mastery_items if m.get("parent_code") is None]
    domain_radar: list[dict] = []
    for dom in top_domains:
        dom_leaves = [
            lf for lf in leaves
            if lf.get("domain") == dom.get("domain") or lf.get("parent_code") == dom["code"] or dom["code"] == lf["code"]
        ]
        # 若节点有 domain 字段，优先按 domain 精准归属，避免三级目录错算
        if dom.get("domain"):
            dom_leaves = [lf for lf in leaves if lf.get("domain") == dom["domain"]]
        tested = [lf for lf in dom_leaves if lf["observed_rate"] is not None]
        avg_rate = round(sum(lf["observed_rate"] for lf in tested) / len(tested), 4) if tested else None
        domain_radar.append({
            "domain_code": dom["code"],
            "domain_name": dom["name"],
            "total_topics": len(dom_leaves),
            "tested_topics": len(tested),
            "mastered_count": sum(1 for lf in dom_leaves if lf["mastery_status"] == "mastered"),
            "weak_count": sum(1 for lf in dom_leaves if lf["mastery_status"] == "weak"),
            "insufficient_count": sum(1 for lf in dom_leaves if lf["mastery_status"] == "insufficient"),
            "untested_count": sum(1 for lf in dom_leaves if lf["mastery_status"] == "untested"),
            "observed_rate": avg_rate,
        })

    return {
        "planning_threshold": threshold,
        "summary_counts": {
            "total_topics": len(leaves),
            "mastered_count": len(strengths),
            "weak_count": len(weaknesses),
            "insufficient_count": len(developing),
            "untested_count": len(untested),
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
        "developing": developing,
        "untested_highlights": untested[:8],
        "domain_radar": domain_radar,
        "disclaimer": "成长状态基于独立首次作答与已审核校卷明细聚合，样本不足时不推算 0 分，不预测中考成绩。",
    }


def compose_practice_plan(
    candidates: list[dict],
    mastery_items: list[dict],
    prerequisite_edges: list[dict],
    target_count: int = 5,
    purpose: str = "training",
    focus_knowledge_code: str | None = None,
) -> dict:
    """基于知识点、题库曝光与学生当前能力缺失综合编制一轮有限题数练习。"""
    if target_count <= 0 or not candidates:
        return {
            "items": [],
            "composition_summary": {
                "weak_count": 0,
                "prereq_count": 0,
                "explore_count": 0,
                "review_count": 0,
                "total_selected": 0,
            },
        }

    mastery_by_code = {m["code"]: m for m in mastery_items}
    weak_codes = {m["code"] for m in mastery_items if m["mastery_status"] == "weak"}
    prereq_of_weak = {
        e["source"]
        for e in prerequisite_edges
        if e.get("target") in weak_codes and e.get("source") not in weak_codes
    }
    explore_codes = {
        m["code"]
        for m in mastery_items
        if m["mastery_status"] in {"insufficient", "untested"}
    }

    eligible = [
        c for c in candidates
        if (purpose != "evaluation" or c.get("seen_count", 0) == 0)
    ]
    if not eligible:
        return {
            "items": [],
            "composition_summary": {
                "weak_count": 0,
                "prereq_count": 0,
                "explore_count": 0,
                "review_count": 0,
                "total_selected": 0,
            },
        }

    def classify_candidate(cand: dict) -> tuple[int, str, str]:
        codes = cand.get("knowledge_codes") or []
        if focus_knowledge_code and focus_knowledge_code in codes:
            name = mastery_by_code.get(focus_knowledge_code, {}).get("name", "指定知识点")
            return (0, "weak", f"定向突破：{name}")
        for code in codes:
            if code in weak_codes:
                name = mastery_by_code.get(code, {}).get("name", "薄弱知识点")
                return (1, "weak", f"薄弱突破：{name}")
        for code in codes:
            if code in prereq_of_weak:
                name = mastery_by_code.get(code, {}).get("name", "前置基础")
                return (2, "prereq", f"前置基础巩固：{name}")
        for code in codes:
            if code in explore_codes:
                name = mastery_by_code.get(code, {}).get("name", "待测知识点")
                return (3, "explore", f"盲区探索：{name}")
        first_name = mastery_by_code.get(codes[0], {}).get("name", "综合知识") if codes else "综合知识"
        return (4, "review", f"优势巩固：{first_name}")

    buckets: dict[str, list[dict]] = {"weak": [], "prereq": [], "explore": [], "review": []}
    for cand in eligible:
        tier_rank, tier_key, reason = classify_candidate(cand)
        enriched = {
            **cand,
            "_tier_rank": tier_rank,
            "_tier_key": tier_key,
            "_reason": reason,
        }
        buckets[tier_key].append(enriched)

    for key in buckets:
        buckets[key].sort(
            key=lambda c: (
                c["_tier_rank"],
                c.get("seen_count", 0),
                c.get("created_sort_key", ""),
                c["question_id"],
            )
        )

    selected: list[dict] = []
    used_qids: set[str] = set()

    def pick_from(bucket_key: str, limit: int) -> None:
        taken = 0
        for cand in buckets[bucket_key]:
            if taken >= limit or len(selected) >= target_count:
                break
            if cand["question_id"] in used_qids:
                continue
            used_qids.add(cand["question_id"])
            selected.append(cand)
            taken += 1

    if purpose == "evaluation":
        # 阶段诊断优先补充待测/证据不足知识点，其次薄弱点验证
        pick_from("explore", max(1, (target_count + 1) // 2))
        pick_from("weak", target_count)
        pick_from("prereq", target_count)
        pick_from("review", target_count)
    else:
        # 综合练习按薄弱(约50%) + 盲区探索(约30%) + 前置/优势巩固(约20%)配比，不足时顺延补齐
        weak_quota = max(1, round(target_count * 0.5)) if (buckets["weak"] or focus_knowledge_code) else 0
        explore_quota = max(1, round(target_count * 0.3)) if buckets["explore"] else 0
        prereq_quota = 1 if buckets["prereq"] and target_count >= 3 else 0
        pick_from("weak", weak_quota)
        pick_from("prereq", prereq_quota)
        pick_from("explore", explore_quota)
        pick_from("review", max(1, target_count - len(selected)))
        # 兜底按优先级补齐剩余名额
        for fallback_key in ("weak", "prereq", "explore", "review"):
            pick_from(fallback_key, target_count)

    counts = {"weak_count": 0, "prereq_count": 0, "explore_count": 0, "review_count": 0}
    items_out = []
    for seq, cand in enumerate(selected, start=1):
        tk = cand["_tier_key"]
        counts[f"{tk}_count"] += 1
        items_out.append({
            "seq": seq,
            "question_id": cand["question_id"],
            "question_version_id": cand["question_version_id"],
            "target_knowledge_codes": cand.get("knowledge_codes") or [],
            "selection_reason": cand["_reason"],
            "focus_tier": tk,
        })

    return {
        "items": items_out,
        "composition_summary": {**counts, "total_selected": len(items_out)},
    }
