#!/usr/bin/env python3
"""只读校验开发环境 SQLite 库中的校考与报告不变量（零写库、零学生 PII/密钥输出）。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = REPO_ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from shutong.school_exam_matcher import build_canonical_exam_key, normalize_grade, reports_represent_same_exam  # noqa: E402

DEFAULT_DEV_DB = Path("/media/xc/backup_ext4/pageboy-home/development/data/shutong-dev.sqlite3")


def audit_database(db_path: Path) -> dict:
    if not db_path.is_file():
        return {"exists": False, "anomalies": [], "summary": {}}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        tables = {r["name"] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "school_exam_reports" not in tables:
            return {"exists": True, "anomalies": [], "summary": {"reports": 0}}

        rep_rows = [
            SimpleNamespace(
                id=r["id"],
                learner_id=r["learner_id"],
                external_exam_id=r["external_exam_id"],
                canonical_exam_key=r["canonical_exam_key"] if "canonical_exam_key" in r.keys() else None,
                academic_year=r["academic_year"],
                grade=r["grade"],
                exam_type=r["exam_type"],
                exam_sequence=r["exam_sequence"],
                title=r["title"],
                exam_date=r["exam_date"],
                answer_card_pages=json.loads(r["answer_card_pages"] or "{}"),
                linked_exam_ids=json.loads(r["linked_exam_ids"] or "[]"),
            )
            for r in cur.execute("SELECT * FROM school_exam_reports ORDER BY created_at DESC")
        ]

        anomalies: list[dict] = []
        for i in range(len(rep_rows)):
            for j in range(i + 1, len(rep_rows)):
                a, b = rep_rows[i], rep_rows[j]
                if a.learner_id != b.learner_id:
                    continue
                a_links = [
                    str(link.get("exam_id") or "")
                    for link in (a.linked_exam_ids or [])
                    if isinstance(link, dict) and link.get("exam_id")
                ]
                if reports_represent_same_exam(
                    a_ext_id=a.external_exam_id,
                    a_year=a.academic_year,
                    a_grade=a.grade,
                    a_type=a.exam_type,
                    a_seq=a.exam_sequence,
                    a_title=a.title,
                    a_date=a.exam_date,
                    a_linked_ids=a_links,
                    b=b,
                ):
                    anomalies.append({"kind": "duplicate_report", "ids": [a.id, b.id]})

        for r in rep_rows:
            expected_ckey = build_canonical_exam_key(
                academic_year=r.academic_year,
                grade=r.grade,
                exam_type=r.exam_type,
                exam_sequence=r.exam_sequence,
                title=r.title,
                exam_date=r.exam_date,
            )
            if expected_ckey and not r.canonical_exam_key:
                anomalies.append({"kind": "missing_canonical_exam_key", "report_id": r.id})

        expected_pages_by_exam: dict[str, set[int]] = {}
        for rep in rep_rows:
            for link in rep.linked_exam_ids or []:
                if isinstance(link, dict) and link.get("exam_id") and link.get("subject"):
                    subj = str(link["subject"])
                    expected_pages_by_exam[str(link["exam_id"])] = {
                        int(p) for p in (rep.answer_card_pages.get(subj) or [])
                    }

        exam_rows = list(cur.execute("SELECT id, subject, grade FROM school_exams"))
        for ex in exam_rows:
            ng = normalize_grade(ex["grade"])
            if ex["grade"] and ng and ex["grade"] != ng:
                anomalies.append({"kind": "grade_alias_drift", "exam_id": ex["id"]})

        att_rows = list(
            cur.execute("SELECT school_exam_id, filename, sha256 FROM school_paper_attachments")
        )
        seen_exam_sha: set[tuple[str, str]] = set()
        exam_subj_map = {ex["id"]: ex["subject"] for ex in exam_rows}
        for att in att_rows:
            key = (att["school_exam_id"], att["sha256"])
            if key in seen_exam_sha:
                anomalies.append({"kind": "duplicate_attachment_sha", "exam_id": att["school_exam_id"]})
            seen_exam_sha.add(key)
            subj = exam_subj_map.get(att["school_exam_id"])
            if subj and att["school_exam_id"] in expected_pages_by_exam:
                allowed = {f"报告答题卡-{subj}-第{p}页.png" for p in expected_pages_by_exam[att["school_exam_id"]]}
                if att["filename"].startswith(f"报告答题卡-{subj}-第") and att["filename"] not in allowed:
                    anomalies.append({"kind": "stale_answer_card", "exam_id": att["school_exam_id"], "filename": att["filename"]})

        return {
            "exists": True,
            "anomalies": anomalies,
            "summary": {
                "reports": len(rep_rows),
                "school_exams": len(exam_rows),
                "attachments": len(att_rows),
                "anomaly_count": len(anomalies),
            },
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only school-exam inventory audit")
    parser.add_argument("--db", type=Path, default=DEFAULT_DEV_DB)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    result = audit_database(args.db)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["exists"]:
            print("ℹ️ 开发库尚未初始化（空库）。")
        else:
            s = result["summary"]
            cnt = s.get("anomaly_count", 0)
            icon = "✅" if cnt == 0 else "⚠️"
            print(f"{icon} 开发库校考不变量体检：报告 {s.get('reports', 0)} 份 / 档案 {s.get('school_exams', 0)} 场 / 附件 {s.get('attachments', 0)} 份 / 异常 {cnt} 项")
            for item in result["anomalies"][:5]:
                print(f"   - {item}")
    if args.strict and result["summary"].get("anomaly_count", 0) > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
