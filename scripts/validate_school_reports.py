#!/usr/bin/env python3
"""两份真实报告 vs Owner 验收检查点（不硬编码进解析器；只读本地 PDF）。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from shutong.school_report_parser import parse_report_pdf  # noqa: E402

# Owner 已给验收值、但 OCR 封面没有年级文字的报告：以人工补录值参与校验（业务解析不猜）。
MANUAL_IDENTITY_OVERRIDES = {"B": {"grade": "9"}}

CHECKPOINTS = {
    "A": {
        "academic_year": "2026-2027",
        "grade": "9",
        "exam_type_prefix": "期中考试",
        "total": (216.5, 440.0),
        "total_class_rank": 16,
        "subjects": {
            "math": (69.0, 100.0),
            "english": (72.5, 100.0),
            "physics": (27.0, 70.0),
            "ethics": (48.0, 70.0),
        },
        "scope": "DIFFERENT_SCOPE_POSSIBLE",
        "cards": {"math": [5, 6, 7, 8], "english": [11, 12], "physics": [15, 16], "ethics": [19, 20]},
    },
    "B": {
        "academic_year": "2026-2027",
        "grade": "9",
        "exam_type_prefix": "统一练习一",
        "total": (240.0, 370.0),
        "total_class_rank": 15,
        "total_participants": 674,
        "subjects": {
            "chinese": (63.0, 100.0),
            "math": (70.0, 100.0),
            "english": (71.0, 100.0),
            "physics": (36.0, 70.0),
            "ethics": (33.0, 50.0),
        },
        "scope": "DIFFERENT_SCOPE_POSSIBLE",
        "cards": {
            "chinese": [5, 6],
            "math": [9, 10, 11, 12],
            "english": [16, 17],
            "physics": [20, 21],
            "ethics": [23, 24],
        },
    },
}


def close(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) < 0.01


def main() -> int:
    inbox = Path("/media/xc/backup_ext4/pageboy-home/development/school-exams/inbox")
    samples = {"A": next(inbox.glob("期中/*分析报告册.pdf")), "B": next(inbox.glob("十月/*分析报告册.pdf"))}
    failed = 0
    for label, path in samples.items():
        data = path.read_bytes()
        doc = parse_report_pdf(data, filename=path.name, digest=hashlib.sha256(data).hexdigest())
        for name, value in MANUAL_IDENTITY_OVERRIDES.get(label, {}).items():
            if getattr(doc.identity, name) in (None, ""):
                setattr(doc.identity, name, value)
        cp = CHECKPOINTS[label]
        results: list[str] = []
        def check(name: str, ok: bool, actual: object) -> None:
            results.append(("PASS" if ok else "FAIL") + f" {name} actual={actual}")

        check("academic_year", doc.identity.academic_year == cp["academic_year"], doc.identity.academic_year)
        check("grade", doc.identity.grade == cp["grade"], doc.identity.grade)
        check("exam_type", bool(doc.identity.exam_type and doc.identity.exam_type.startswith(cp["exam_type_prefix"])), doc.identity.exam_type)
        check("total_score", close(doc.report_total_score, cp["total"][0]), doc.report_total_score)
        check("total_max", close(doc.report_total_max, cp["total"][1]), doc.report_total_max)
        check("total_class_rank", doc.total_class_rank == cp["total_class_rank"], doc.total_class_rank)
        if "total_participants" in cp:
            check("total_participants", doc.total_participants == cp["total_participants"], doc.total_participants)
        check("scope", doc.scope_status == cp["scope"], doc.scope_status)
        parsed_subjects = {item.subject: (item.score, item.max_score) for item in doc.subjects}
        for subject, expected in cp["subjects"].items():
            actual = parsed_subjects.get(subject)
            check(f"subject:{subject}", actual is not None and close(actual[0], expected[0]) and close(actual[1], expected[1]), actual)
        check("cards", doc.answer_card_pages == cp["cards"], doc.answer_card_pages)
        check("questions_count", len(doc.questions) > 0, len(doc.questions))
        failed += sum(1 for item in results if item.startswith("FAIL"))
        print(f"\n[{label}] pages={doc.pages} sha256={doc.identity.source_sha256}")
        for item in results:
            print(" ", item)
    print(f"\nFAILED={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
