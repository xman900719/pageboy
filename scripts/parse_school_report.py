#!/usr/bin/env python3
"""本地分析报告册解析 CLI：只读 PDF，输出脱敏摘要，不访问数据库或网络。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from shutong.school_report_parser import parse_report_pdf  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="解析书童校考分析报告册（本地 OCR，不联网）")
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    if not args.pdf.is_file():
        print("PDF_NOT_FOUND", file=sys.stderr)
        return 2
    data = args.pdf.read_bytes()
    report = parse_report_pdf(data, filename=args.pdf.name, digest=hashlib.sha256(data).hexdigest())
    payload = report.as_dict()
    payload.pop("text_excerpt", None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
