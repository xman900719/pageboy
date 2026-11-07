#!/usr/bin/env python3
"""只读审计北京中考真题目录：真实计算 SHA256、页数、文本层，并按采录规则分类。不复制、不修改任何原件。

用法：python scripts/audit_exam_corpus.py <真题目录> <输出JSON>
"""
from __future__ import annotations
import hashlib, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/api"))
from shutong.private_files import DOCX_MEDIA_TYPE, extract_docx_text, pdf_needs_ocr, validate_file  # noqa: E402
from shutong.research import official_reject_reason  # noqa: E402

SUBJECTS = {"语文": "chinese", "数学": "math", "英语": "english", "物理": "physics"}


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def classify(path: Path) -> dict:
    name = path.name
    subject = next((v for k, v in SUBJECTS.items() if k in name), None)
    year = re.search(r"(20\d\d)", name)
    yr = int(year.group(1)) if year else None
    reasons = []
    if subject is None:
        reasons.append("NOT_FOUR_SUBJECTS")
    reason = official_reject_reason(name)
    if reason:
        reasons.append(reason)
    if "候选" in name:
        reasons.append("CANDIDATE_NAME_ONLY_UNVERIFIED_ORIGIN")  # 文件名不能作为真实性依据
    carrier_note = None
    if yr in (2019, 2020) and subject is not None and reason == "THIRD_PARTY_ANALYSIS_NOT_OFFICIAL":
        carrier_note = "OFFICIAL_QUESTIONS_EMBEDDED_IN_ANALYSIS_PDF"
    return {
        "subject": subject,
        "year": yr,
        "reject_reasons": reasons,
        "carrier_note": carrier_note,
    }


def main(root: str, out: str) -> None:
    items = []
    root_path = Path(root)
    all_files = sorted(
        p for p in root_path.rglob("*")
        if p.is_file() and p.suffix.lower() in (".pdf", ".docx")
    )
    for p in all_files:
        raw = p.read_bytes()
        h = hashlib.sha256(raw).hexdigest()
        rel = str(p.relative_to(root_path))
        if p.suffix.lower() == ".pdf":
            info = run(["pdfinfo", str(p)])
            pages = re.search(r"Pages:\s+(\d+)", info)
            extracted_text = run(["pdftotext", str(p), "-"])
            text_chars = len(extracted_text.strip())
            items.append({
                "path": rel,
                "sha256": h,
                "bytes": len(raw),
                "valid_pdf": pages is not None,
                "pages": int(pages.group(1)) if pages else None,
                "text_chars": text_chars,
                "needs_ocr": pdf_needs_ocr(extracted_text),
                **classify(p),
            })
        else:
            try:
                validate_file(raw, DOCX_MEDIA_TYPE)
                extracted_text = extract_docx_text(raw)
                valid_docx = True
            except Exception:
                extracted_text = ""
                valid_docx = False
            items.append({
                "path": rel,
                "sha256": h,
                "bytes": len(raw),
                "valid_docx": valid_docx,
                "pages": None,
                "text_chars": len(extracted_text.strip()),
                "needs_ocr": False,
                **classify(p),
            })
    seen: dict[str, str] = {}
    for it in items:
        it["duplicate_of"] = seen.get(it["sha256"])
        seen.setdefault(it["sha256"], it["path"])
        it["official_candidate"] = (
            not it["reject_reasons"]
            or it["reject_reasons"] == ["CANDIDATE_NAME_ONLY_UNVERIFIED_ORIGIN"]
            or it.get("carrier_note") == "OFFICIAL_QUESTIONS_EMBEDDED_IN_ANALYSIS_PDF"
        )
    Path(out).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} files audited; four-subject official candidates: {sum(i['official_candidate'] for i in items)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
