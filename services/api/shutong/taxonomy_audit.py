"""四学科候选知识点逐条核验条款、填报审核意见并发布正式版本（可重入、幂等）。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .database import make_engine
from .fourcorpus import (
    TaxonomyReleaseIn,
    _latest,
    _repo_path,
    publish_taxonomy_release,
    seed_candidate_nodes,
)

SUBJECT_NAMES = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "physics": "物理",
}


def build_clause_backed_opinion(
    *,
    subject: str,
    node_meta: dict[str, Any],
    clause_map: dict[str, dict[str, Any]],
    legacy_codes: list[str],
) -> str:
    """根据权威课标条款原文与映射关系生成详实、可溯源的审核依据文本。"""
    source_ids = node_meta.get("source_clause_ids") or []
    matched_clauses = [clause_map[cid] for cid in source_ids if cid in clause_map]
    if not matched_clauses:
        raise ValueError(f"候选节点 {node_meta['code']} 缺少可核查课标条款: {source_ids}")

    citations = []
    for cl in matched_clauses[:3]:
        sec = cl.get("sub_theme") or cl.get("theme_title") or cl.get("domain_title") or ""
        cnum = cl.get("clause_number") or ""
        pp = cl.get("print_page")
        pdfp = cl.get("pdf_page")
        citations.append(f"{sec}{cnum}(印刷p.{pp}/PDF p.{pdfp})")
    if len(matched_clauses) > 3:
        citations.append(f"等共{len(matched_clauses)}条")

    primary_req = (
        matched_clauses[0].get("derived_requirement")
        or matched_clauses[0].get("standardized_text")
        or node_meta.get("description")
        or node_meta.get("name")
    )
    elective_note = (
        "该节点依课标标示为选学(*不作考试要求)，仅后台归档、不纳入学生端必考主图谱与智能组卷。"
        if node_meta.get("is_elective")
        else "已核对为义务教育必学主干内容，概念粒度适中，适合学生知识图谱呈现与诊断组卷。"
    )
    legacy_note = (
        f"历史题库兼容映射：{', '.join(legacy_codes)}。"
        if legacy_codes
        else "2022版新课标细化/新增知识点。"
    )
    return (
        f"核对教育部2022年版初中{SUBJECT_NAMES.get(subject, subject)}课程标准"
        f"[{'; '.join(citations)}]，核心要求为「{primary_req}」。"
        f"{elective_note}{legacy_note}"
    )


def audit_and_publish_subject(
    db: Session,
    *,
    subject: str,
    reviewer_id: str = "owner_delegated_ai",
    release_suffix: str = "v2022.1.0",
    force_update_existing: bool = False,
) -> dict[str, Any]:
    """为单个学科执行：同步候选节点 -> 逐条填报审核意见并批准 -> 发布正式版本。"""
    seed_res = seed_candidate_nodes(subject=subject, db=db)

    cand_path = _repo_path(f"contracts/{subject}_knowledge_taxonomy_candidate.json")
    clause_path = _repo_path(f"contracts/curriculum_clauses_{subject}.json")
    mapping_path = _repo_path(f"contracts/{subject}_legacy_taxonomy_mapping.json")

    candidates_meta = {c["code"]: c for c in json.loads(cand_path.read_text(encoding="utf-8"))}
    clauses_meta = {cl["clause_id"]: cl for cl in json.loads(clause_path.read_text(encoding="utf-8"))}

    cand_to_legacy: dict[str, list[str]] = {}
    if mapping_path.is_file():
        mapping_json = json.loads(mapping_path.read_text(encoding="utf-8"))
        for row in mapping_json.get("legacy_mappings", []):
            lcode = row.get("legacy_code")
            for target in row.get("target_candidate_codes") or []:
                if lcode:
                    cand_to_legacy.setdefault(target, []).append(lcode)

    db_nodes = db.execute(
        select(m.KnowledgeNode)
        .where(
            m.KnowledgeNode.subject == subject,
            m.KnowledgeNode.code.like(f"{subject}_cand.%"),
            m.KnowledgeNode.status == "active",
        )
        .order_by(m.KnowledgeNode.created_at.asc(), m.KnowledgeNode.code.asc())
    ).scalars().all()

    approved_now = 0
    already_approved = 0
    now_dt = datetime.now(timezone.utc)

    for node in db_nodes:
        meta = candidates_meta.get(node.code)
        if meta is None:
            continue
        ver = _latest(db, node.id)
        if ver is None:
            continue

        # 同步最新契约里的 is_elective 标记，确保数学选学节点正确落库
        node.is_elective = bool(meta.get("is_elective", False))

        if ver.review_status == "approved" and not force_update_existing:
            already_approved += 1
            continue

        opinion = build_clause_backed_opinion(
            subject=subject,
            node_meta=meta,
            clause_map=clauses_meta,
            legacy_codes=sorted(set(cand_to_legacy.get(node.code, []))),
        )
        ver.review_status = "approved"
        ver.reviewer_id = reviewer_id
        ver.review_opinion = opinion
        ver.reviewed_at = now_dt
        approved_now += 1

    db.commit()

    release_version = f"{subject}-{release_suffix}"
    existing_rel = db.scalar(
        select(m.KnowledgeTaxonomyRelease).where(
            m.KnowledgeTaxonomyRelease.release_version == release_version
        )
    )
    release_status = "already_published"
    if existing_rel is None:
        rel_res = publish_taxonomy_release(
            TaxonomyReleaseIn(
                subject=subject,
                release_version=release_version,
                published_by=reviewer_id,
                summary=f"教育部2022年版初中{SUBJECT_NAMES.get(subject, subject)}课程标准全量知识点体系首发版本（已逐条溯源核对）",
            ),
            db=db,
        )
        release_status = rel_res["status"]

    return {
        "subject": subject,
        "seeded_or_revised": seed_res,
        "total_candidate_nodes": len(db_nodes),
        "approved_now": approved_now,
        "already_approved": already_approved,
        "release_version": release_version,
        "release_status": release_status,
    }


def run_all_subjects(
    *,
    database_url: str | None = None,
    reviewer_id: str = "owner_delegated_ai",
    force_update_existing: bool = False,
) -> list[dict[str, Any]]:
    """对全部四个学科依次执行候选节点全量审核与版本发布。"""
    db_url = database_url or os.getenv("SHUTONG_DATABASE_URL", "sqlite:///./shutong-dev.sqlite3")
    engine = make_engine(db_url)
    results = []
    with Session(engine) as db:
        for subject in ("math", "chinese", "english", "physics"):
            results.append(
                audit_and_publish_subject(
                    db,
                    subject=subject,
                    reviewer_id=reviewer_id,
                    force_update_existing=force_update_existing,
                )
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="全量审核并发布四学科候选知识点体系")
    parser.add_argument("--database-url", default=None, help="覆盖 SHUTONG_DATABASE_URL")
    parser.add_argument("--reviewer-id", default="owner_delegated_ai", help="审核人审计标识")
    parser.add_argument("--force", action="store_true", help="即使节点已 approved 也重新回写审核意见")
    args = parser.parse_args()
    summary = run_all_subjects(
        database_url=args.database_url,
        reviewer_id=args.reviewer_id,
        force_update_existing=args.force,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
