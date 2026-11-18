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


SCHOOL_ERROR_CATEGORIES: tuple[str, ...] = (
    "concept",
    "calculation",
    "reading",
    "method",
    "norm",
    "other",
)

_SCHOOL_CATEGORY_ORDER: dict[str, int] = {
    cat: idx for idx, cat in enumerate(SCHOOL_ERROR_CATEGORIES)
}
_SCHOOL_CATEGORY_ORDER["uncategorized"] = len(SCHOOL_ERROR_CATEGORIES)


def question_label_sort_key(label: str) -> tuple[int, tuple[int, ...], str]:
    """按题号中的数字序列自然升序排序（如 1, 2, ..., 10），无数字项排在末尾。"""
    nums: list[int] = []
    buf: list[str] = []
    for ch in label or "":
        if "0" <= ch <= "9":
            buf.append(ch)
        elif buf:
            nums.append(int("".join(buf)))
            buf.clear()
    if buf:
        nums.append(int("".join(buf)))
    return (0 if nums else 1, tuple(nums), label or "")

SCHOOL_ERROR_CATEGORY_LABELS: dict[str, str] = {
    "concept": "概念/公式不清",
    "calculation": "运算/粗心失误",
    "reading": "审题/条件遗漏",
    "method": "思路/方法受阻",
    "norm": "步骤/书写不规范",
    "other": "其他原因",
    "uncategorized": "未归类错因",
}


def _resolve_practice_match(
    knowledge_id: str,
    mastery_by_code: dict[str, dict],
    knowledge_alias_map: dict[str, list[str]] | None,
) -> dict | None:
    """在日常练习掌握度映射表中匹配当前考点或其对应新课标节点（优先保留薄弱警示）。"""
    lookup_codes = [knowledge_id]
    if knowledge_alias_map:
        for alias in knowledge_alias_map.get(knowledge_id, ()):
            if alias not in lookup_codes:
                lookup_codes.append(alias)
    matches = [mastery_by_code[c] for c in lookup_codes if c in mastery_by_code]
    if not matches:
        return None
    status_priority = {"weak": 0, "insufficient": 1, "mastered": 2, "untested": 3}
    matches.sort(
        key=lambda m: (
            status_priority.get(m.get("mastery_status", "untested"), 9),
            m.get("observed_rate") if m.get("observed_rate") is not None else 1.0,
            -int(m.get("sample_size", 0)),
        )
    )
    return matches[0]


def _classify_cross_diagnosis(has_taxonomy: bool, practice_match: dict | None) -> tuple[str, float | None, int, str]:
    """根据日常独立作答掌握状态与校考失分生成纯规则交叉诊断标签。"""
    if not has_taxonomy:
        return ("not_applicable", None, 0, "archive_review")
    if practice_match is None:
        return ("untested", None, 0, "blind_spot")
    status = practice_match.get("mastery_status", "untested")
    rate = practice_match.get("observed_rate")
    samples = int(practice_match.get("sample_size", 0))
    if status == "weak":
        return ("weak", rate, samples, "double_weak")
    if status == "mastered":
        return ("mastered", rate, samples, "exam_slip")
    return (status, rate, samples, "blind_spot")


def _aggregate_recurring_losses(
    exams_by_id: dict[str, dict],
    current_lost_kids: set[str],
) -> tuple[int, list[dict]]:
    """聚合跨多次校考重复扣分的知识点（同一科目至少在 2 场不同校考中均出现失分）。"""
    per_kid_hits: dict[str, list[dict]] = defaultdict(list)
    exams_with_confirmed_items = 0

    sorted_exams = sorted(
        exams_by_id.values(),
        key=lambda e: (str(e.get("exam_date", "")), str(e.get("exam_id", ""))),
        reverse=True,
    )
    for ex in sorted_exams:
        confirmed = [
            it
            for it in (ex.get("items") or [])
            if it.get("confirmed_by_user") and float(it.get("max_points", 0.0)) > 0
        ]
        if confirmed:
            exams_with_confirmed_items += 1
        per_exam_kid: dict[str, dict] = {}
        for it in confirmed:
            max_pts = float(it["max_points"])
            earned_pts = float(it["earned_points"])
            if earned_pts >= max_pts:
                continue
            lost = max_pts - earned_pts
            kid = str(it["knowledge_id"])
            bucket = per_exam_kid.setdefault(
                kid,
                {
                    "exam_id": str(ex["exam_id"]),
                    "title": str(ex.get("title", "")),
                    "exam_date": str(ex.get("exam_date", "")),
                    "knowledge_name": str(it.get("knowledge_name") or kid),
                    "lost_points": 0.0,
                    "item_count": 0,
                    "categories": set(),
                },
            )
            bucket["lost_points"] += lost
            bucket["item_count"] += 1
            cat = it.get("error_category")
            if cat in _SCHOOL_CATEGORY_ORDER and cat != "uncategorized":
                bucket["categories"].add(cat)
        for kid, bucket in per_exam_kid.items():
            per_kid_hits[kid].append(bucket)

    recurring: list[dict] = []
    for kid, hits in per_kid_hits.items():
        if len(hits) < 2:
            continue
        all_cats = sorted(
            {c for h in hits for c in h["categories"]},
            key=lambda c: _SCHOOL_CATEGORY_ORDER.get(c, 99),
        )
        recurring.append(
            {
                "knowledge_id": kid,
                "knowledge_name": hits[0]["knowledge_name"],
                "exam_count": len(hits),
                "total_lost_points": round(sum(h["lost_points"] for h in hits), 2),
                "total_item_count": sum(h["item_count"] for h in hits),
                "repeat_in_current_exam": kid in current_lost_kids,
                "categories": all_cats,
                "exams": [
                    {
                        "exam_id": h["exam_id"],
                        "title": h["title"],
                        "exam_date": h["exam_date"],
                        "lost_points": round(h["lost_points"], 2),
                        "item_count": h["item_count"],
                    }
                    for h in hits
                ],
            }
        )

    recurring.sort(
        key=lambda r: (
            0 if r["repeat_in_current_exam"] else 1,
            -r["exam_count"],
            -r["total_lost_points"],
            r["knowledge_id"],
        )
    )
    return exams_with_confirmed_items, recurring


def analyze_school_exam_errors(
    exam_meta: dict,
    exam_items: list[dict],
    history_exams: list[dict],
    practice_mastery: list[dict] | None = None,
    has_taxonomy: bool = True,
    knowledge_alias_map: dict[str, list[str]] | None = None,
) -> dict:
    """纯函数：计算单场校考失分结构、错因占比、日常掌握度交叉诊断及同科历次顽固失分点对比。

    红线约束：
    - 未确认的 OCR 草稿小题（confirmed_by_user=False）不得纳入正式分析（AC-EVI-02）；
    - 无已确认明细时返回 status='insufficient_items'，绝不根据总分推算考点错因（INV-05 / AC-GAP-01）；
    - 仅以当前可核实条目如实聚合，缺失即显示不足或未归类。
    """
    exam_id = str(exam_meta["id"])
    exam_confirmed = bool(exam_meta.get("confirmed_by_user"))
    exam_earned = float(exam_meta.get("earned_points", 0.0))
    exam_max = float(exam_meta.get("max_points", 0.0))
    paper_lost_points = round(max(0.0, exam_max - exam_earned), 2) if exam_confirmed else None

    confirmed_items = [
        it
        for it in exam_items
        if it.get("confirmed_by_user") and float(it.get("max_points", 0.0)) > 0
    ]
    unconfirmed_draft_count = sum(1 for it in exam_items if not it.get("confirmed_by_user"))

    # 合并本场与同科历史场次（按 exam_id 去重，确保无论调用方是否已含本场都能精确统计跨场次重复扣分）
    exams_by_id: dict[str, dict] = {}
    for hx in history_exams:
        hx_id = str(hx.get("exam_id") or hx.get("id"))
        exams_by_id[hx_id] = {**hx, "exam_id": hx_id}
    exams_by_id[exam_id] = {
        "exam_id": exam_id,
        "title": exam_meta.get("title", ""),
        "exam_date": str(exam_meta.get("exam_date", "")),
        "earned_points": exam_earned,
        "max_points": exam_max,
        "confirmed_by_user": exam_confirmed,
        "items": exam_items,
    }

    itemized_max = round(sum(float(it["max_points"]) for it in confirmed_items), 2)
    itemized_earned = round(sum(float(it["earned_points"]) for it in confirmed_items), 2)
    lost_items_raw = [
        it for it in confirmed_items if float(it["earned_points"]) < float(it["max_points"])
    ]
    itemized_lost = round(
        sum(float(it["max_points"]) - float(it["earned_points"]) for it in lost_items_raw), 2
    )
    unaccounted_lost = (
        round(max(0.0, paper_lost_points - itemized_lost), 2)
        if paper_lost_points is not None
        else None
    )

    current_lost_kids = {str(it["knowledge_id"]) for it in lost_items_raw}
    exams_with_items_count, recurring_knowledge = _aggregate_recurring_losses(
        exams_by_id, current_lost_kids
    )
    history_summary = {
        "same_subject_exam_count": len(exams_by_id),
        "same_subject_exams_with_items": exams_with_items_count,
        "recurring_count": len(recurring_knowledge),
    }

    base_overview = {
        "confirmed_item_count": len(confirmed_items),
        "lost_item_count": len(lost_items_raw),
        "unconfirmed_draft_count": unconfirmed_draft_count,
        "earned_points": round(exam_earned, 2),
        "max_points": round(exam_max, 2),
        "paper_lost_points": paper_lost_points,
        "itemized_earned_points": itemized_earned,
        "itemized_max_points": itemized_max,
        "itemized_lost_points": itemized_lost,
        "unaccounted_lost_points": unaccounted_lost,
        "categorized_item_count": 0,
        "uncategorized_item_count": 0,
        "primary_error_category": None,
        "primary_knowledge_id": None,
        "primary_knowledge_name": None,
    }
    disclaimer = "错因分析仅基于已人工核对的逐题失分明细，学校考试总分不拆解考点、不作中考预测；平时表现采用日常练习与诊断独立作答数据对照。"

    if not confirmed_items:
        if unconfirmed_draft_count > 0:
            summary = f"当前仅有 {unconfirmed_draft_count} 条未确认的 OCR 草稿小题，人工核对确认前不纳入正式错误分析。"
        elif exam_confirmed:
            summary = "当前仅登记了试卷总分，尚无已核对的逐题失分明细；依据诚实口径不从总分推算考点与错因。"
        else:
            summary = "当前档案尚无已核对总分与逐题明细，暂不足以生成错误分析。"
        return {
            "exam_id": exam_id,
            "subject": exam_meta["subject"],
            "title": exam_meta["title"],
            "exam_date": str(exam_meta["exam_date"]),
            "confirmed_by_user": exam_confirmed,
            "has_taxonomy": has_taxonomy,
            "status": "insufficient_items",
            "overview": base_overview,
            "diagnosis_summary": summary,
            "by_category": [],
            "by_knowledge": [],
            "lost_items": [],
            "history_summary": history_summary,
            "recurring_knowledge": recurring_knowledge,
            "disclaimer": disclaimer,
        }

    if not lost_items_raw:
        if paper_lost_points is not None and paper_lost_points > 0:
            summary = (
                f"已核对的 {len(confirmed_items)} 道小题当前均为满分，但卷面总分仍有 "
                f"{paper_lost_points:g} 分失分尚未拆解录入明细，可前往「逐题得分与考点」继续补充。"
            )
        else:
            summary = f"已核对的 {len(confirmed_items)} 道小题均为满分，本场暂无失分记录。"
        return {
            "exam_id": exam_id,
            "subject": exam_meta["subject"],
            "title": exam_meta["title"],
            "exam_date": str(exam_meta["exam_date"]),
            "confirmed_by_user": exam_confirmed,
            "has_taxonomy": has_taxonomy,
            "status": "no_errors_recorded",
            "overview": base_overview,
            "diagnosis_summary": summary,
            "by_category": [],
            "by_knowledge": [],
            "lost_items": [],
            "history_summary": history_summary,
            "recurring_knowledge": recurring_knowledge,
            "disclaimer": disclaimer,
        }

    # 1. 按错因分类聚合
    cat_buckets: dict[str, dict] = {}
    categorized_count = 0
    uncategorized_count = 0
    for it in lost_items_raw:
        raw_cat = it.get("error_category")
        cat = raw_cat if raw_cat in SCHOOL_ERROR_CATEGORIES else "uncategorized"
        if cat == "uncategorized":
            uncategorized_count += 1
        else:
            categorized_count += 1
        lost = float(it["max_points"]) - float(it["earned_points"])
        entry = cat_buckets.setdefault(
            cat,
            {"category": cat, "item_count": 0, "lost_points": 0.0, "question_labels": []},
        )
        entry["item_count"] += 1
        entry["lost_points"] += lost
        entry["question_labels"].append(str(it["question_label"]))

    by_category: list[dict] = []
    for entry in cat_buckets.values():
        lost_rounded = round(entry["lost_points"], 2)
        share = round(lost_rounded / itemized_lost, 4) if itemized_lost > 0 else 0.0
        by_category.append(
            {
                "category": entry["category"],
                "item_count": entry["item_count"],
                "lost_points": lost_rounded,
                "share_of_itemized_loss": share,
                "question_labels": sorted(entry["question_labels"], key=question_label_sort_key),
            }
        )
    by_category.sort(
        key=lambda c: (
            -c["lost_points"],
            -c["item_count"],
            _SCHOOL_CATEGORY_ORDER.get(c["category"], 99),
        )
    )

    # 2. 按知识点聚合并与日常练习掌握度交叉诊断
    kid_totals: dict[str, dict] = {}
    for it in confirmed_items:
        kid = str(it["knowledge_id"])
        kt = kid_totals.setdefault(
            kid,
            {
                "knowledge_id": kid,
                "knowledge_name": str(it.get("knowledge_name") or kid),
                "item_count": 0,
                "lost_item_count": 0,
                "earned_points": 0.0,
                "max_points": 0.0,
                "lost_points": 0.0,
                "categories": set(),
                "question_labels": [],
                "notes": [],
            },
        )
        earned = float(it["earned_points"])
        max_pts = float(it["max_points"])
        kt["item_count"] += 1
        kt["earned_points"] += earned
        kt["max_points"] += max_pts
        if earned < max_pts:
            kt["lost_item_count"] += 1
            kt["lost_points"] += max_pts - earned
            kt["question_labels"].append(str(it["question_label"]))
            cat = it.get("error_category")
            if cat in SCHOOL_ERROR_CATEGORIES:
                kt["categories"].add(cat)
            note = (it.get("error_note") or "").strip()
            if note:
                kt["notes"].append({"question_label": str(it["question_label"]), "note": note})

    mastery_by_code = {str(m["code"]): m for m in (practice_mastery or []) if m.get("code")}
    by_knowledge: list[dict] = []
    for kid, kt in kid_totals.items():
        if kt["lost_item_count"] == 0:
            continue
        lost_rounded = round(kt["lost_points"], 2)
        max_rounded = round(kt["max_points"], 2)
        earned_rounded = round(kt["earned_points"], 2)
        obs_rate = round(earned_rounded / max_rounded, 4) if max_rounded > 0 else 0.0
        share = round(lost_rounded / itemized_lost, 4) if itemized_lost > 0 else 0.0
        match = _resolve_practice_match(kid, mastery_by_code, knowledge_alias_map)
        p_status, p_rate, p_samples, diag_tag = _classify_cross_diagnosis(has_taxonomy, match)
        cats = sorted(kt["categories"], key=lambda c: _SCHOOL_CATEGORY_ORDER.get(c, 99))
        by_knowledge.append(
            {
                "knowledge_id": kid,
                "knowledge_name": kt["knowledge_name"],
                "item_count": kt["item_count"],
                "lost_item_count": kt["lost_item_count"],
                "earned_points": earned_rounded,
                "max_points": max_rounded,
                "lost_points": lost_rounded,
                "exam_observed_rate": obs_rate,
                "share_of_itemized_loss": share,
                "categories": cats,
                "question_labels": sorted(kt["question_labels"], key=question_label_sort_key),
                "notes": kt["notes"],
                "practice_status": p_status,
                "practice_observed_rate": p_rate,
                "practice_sample_size": p_samples,
                "diagnosis_tag": diag_tag,
            }
        )
    by_knowledge.sort(
        key=lambda k: (-k["lost_points"], k["exam_observed_rate"], k["knowledge_id"])
    )

    # 3. 失分小题明细清单
    lost_items_out = [
        {
            "id": str(it["id"]),
            "question_label": str(it["question_label"]),
            "knowledge_id": str(it["knowledge_id"]),
            "knowledge_name": str(it.get("knowledge_name") or it["knowledge_id"]),
            "earned_points": round(float(it["earned_points"]), 2),
            "max_points": round(float(it["max_points"]), 2),
            "lost_points": round(float(it["max_points"]) - float(it["earned_points"]), 2),
            "error_category": it.get("error_category") if it.get("error_category") in SCHOOL_ERROR_CATEGORIES else None,
            "error_note": (it.get("error_note") or "").strip() or None,
        }
        for it in lost_items_raw
    ]
    lost_items_out.sort(key=lambda x: (-x["lost_points"], question_label_sort_key(x["question_label"])))

    # 4. 首要错因与综述文案
    tagged_cats = [c for c in by_category if c["category"] != "uncategorized"]
    primary_cat = tagged_cats[0]["category"] if tagged_cats else (by_category[0]["category"] if by_category else None)
    primary_kn = by_knowledge[0] if by_knowledge else None

    repeat_hits = [r for r in recurring_knowledge if r["repeat_in_current_exam"]]
    cat_phrase = (
        f"，主要错因为「{SCHOOL_ERROR_CATEGORY_LABELS.get(primary_cat, primary_cat)}」"
        if primary_cat and primary_cat != "uncategorized"
        else ""
    )
    kn_phrase = f"，首要失分考点为「{primary_kn['knowledge_name']}」" if primary_kn else ""
    repeat_phrase = f"；其中 {len(repeat_hits)} 个考点在同科历次校考中再次失分" if repeat_hits else ""
    gap_phrase = (
        f"（另有 {unaccounted_lost:g} 分卷面失分尚未录入逐题明细）"
        if unaccounted_lost is not None and unaccounted_lost > 0
        else ""
    )
    summary = (
        f"本场已核对失分共 {len(lost_items_raw)} 题（已归因 -{itemized_lost:g} 分）"
        f"{kn_phrase}{cat_phrase}{repeat_phrase}{gap_phrase}。"
    )

    overview = {
        **base_overview,
        "categorized_item_count": categorized_count,
        "uncategorized_item_count": uncategorized_count,
        "primary_error_category": primary_cat,
        "primary_knowledge_id": primary_kn["knowledge_id"] if primary_kn else None,
        "primary_knowledge_name": primary_kn["knowledge_name"] if primary_kn else None,
    }

    return {
        "exam_id": exam_id,
        "subject": exam_meta["subject"],
        "title": exam_meta["title"],
        "exam_date": str(exam_meta["exam_date"]),
        "confirmed_by_user": exam_confirmed,
        "has_taxonomy": has_taxonomy,
        "status": "analyzed",
        "overview": overview,
        "diagnosis_summary": summary,
        "by_category": by_category,
        "by_knowledge": by_knowledge,
        "lost_items": lost_items_out,
        "history_summary": history_summary,
        "recurring_knowledge": recurring_knowledge,
        "disclaimer": disclaimer,
    }
