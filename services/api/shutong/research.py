"""真题连续性与命题研究的纯业务计算：不依赖 HTTP、数据库或模型 SDK。"""
from __future__ import annotations
from collections import Counter

RULE_VERSION = "stats-v1"
SUBJECTS = ("chinese", "math", "english", "physics")
DISTRICTS = ("东城", "西城", "海淀", "朝阳", "丰台", "石景山", "房山", "通州", "顺义", "昌平", "大兴", "门头沟", "怀柔", "平谷", "密云", "延庆", "燕山")
MIN_PRIOR_YEARS = 2
TOP_K = 5


def official_reject_reason(title: str) -> str | None:
    """北京市官方真题采录规则：区县卷与第三方逐题解析不得以 official_exam 身份入库。"""
    if any(d in title for d in DISTRICTS):
        return "DISTRICT_PAPER_REJECTED"
    if "解析" in title:
        return "THIRD_PARTY_ANALYSIS_NOT_OFFICIAL"
    return None


def coverage_report(docs: list[dict], year_from: int, year_to: int) -> dict:
    """docs: {id,subject,exam_year,sha256,ingest_status,verified,review_status,
    question_count,reviewed_question_count}；两个计数均按逻辑题去重。

    采录覆盖与质量审核使用不同状态：missing → recorded → ingested → reviewed。
    """
    by_key: dict[tuple[int, str], list[dict]] = {}
    for d in docs:
        by_key.setdefault((d["exam_year"], d["subject"]), []).append(d)
    cells, gaps = [], []
    for year in range(year_from, year_to + 1):
        for subject in SUBJECTS:
            items = by_key.get((year, subject), [])
            if not items:
                status = "missing"
            elif any(i["review_status"] == "approved" and i["verified"] and i.get("reviewed_question_count", 0) > 0 for i in items):
                status = "reviewed"
            elif any(i["ingest_status"] == "ingested" and i["question_count"] > 0 for i in items):
                status = "ingested"
            else:
                status = "recorded"
            cells.append({"year": year, "subject": subject, "status": status, "documents": [i["id"] for i in items]})
            if status != "reviewed":
                gaps.append({"year": year, "subject": subject, "status": status})
    hashes = Counter(d["sha256"] for d in docs if d.get("sha256"))
    duplicates = sorted(h for h, n in hashes.items() if n > 1)
    return {"year_from": year_from, "year_to": year_to, "cells": cells, "gaps": gaps, "duplicate_sha256": duplicates,
            "note": "仅依据已登记来源计算；未登记即 missing，不推断文件是否存在于磁盘。"}


def _scope(rows: list[dict], target_year: int) -> list[dict]:
    """时间边界：只允许使用目标年份之前的数据，严禁未来信息。"""
    return [r for r in rows if r["year"] < target_year]


def statistics(rows: list[dict], target_year: int) -> dict:
    """rows: {year, kind, knowledge: [code]}，调用方负责只传入 official_exam 且已审核的数据。"""
    used = _scope(rows, target_year)
    years = sorted({r["year"] for r in used})
    kinds = Counter(r["kind"] for r in used)
    knowledge = Counter(k for r in used for k in r["knowledge"])
    return {"rule_version": RULE_VERSION, "target_year": target_year, "years_used": years, "question_count": len(used),
            "kind_distribution": dict(kinds), "knowledge_frequency": dict(knowledge.most_common())}


def predict(rows: list[dict], target_year: int) -> dict:
    """按历史出现年份数排序给出重点知识点候选；这是统计频次，不是中考成绩或命中率承诺。"""
    used = _scope(rows, target_year)
    years = sorted({r["year"] for r in used})
    if len(years) < MIN_PRIOR_YEARS:
        return {"status": "insufficient_evidence", "years_used": years, "candidates": []}
    seen_in: dict[str, set[int]] = {}
    for r in used:
        for k in r["knowledge"]:
            seen_in.setdefault(k, set()).add(r["year"])
    ranked = sorted(seen_in.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:TOP_K]
    return {"status": "statistical_candidates", "years_used": years, "candidates": [{"knowledge": k, "years_seen": len(y)} for k, y in ranked]}


def backtest(rows: list[dict]) -> dict:
    """逐年回测：预测第 Y 年时仅使用 <Y 的数据，与第 Y 年实际知识点对比。"""
    results = []
    for year in sorted({r["year"] for r in rows}):
        pred = predict(rows, year)
        if pred["status"] != "statistical_candidates":
            results.append({"year": year, "status": "insufficient_evidence"})
            continue
        actual = {k for r in rows if r["year"] == year for k in r["knowledge"]}
        hits = [c["knowledge"] for c in pred["candidates"] if c["knowledge"] in actual]
        results.append({"year": year, "status": "evaluated", "predicted": [c["knowledge"] for c in pred["candidates"]], "hits": hits, "hit_count": len(hits), "k": len(pred["candidates"])})
    evaluated = [r for r in results if r["status"] == "evaluated"]
    summary = {"evaluated_years": len(evaluated), "hit_rate": round(sum(r["hit_count"] for r in evaluated) / sum(r["k"] for r in evaluated), 4)} if evaluated else {"evaluated_years": 0, "hit_rate": None, "note": "证据不足，无法有效验证"}
    return {"rule_version": RULE_VERSION, "results": results, "summary": summary}
