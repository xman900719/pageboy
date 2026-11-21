"""图像型 PDF 报告册的 OCR 表结构还原（本地 tesseract/pdftoppm，不访问网络）。

与 school_report_parser 的分工：本模块负责逐页渲染、逐词坐标 OCR 与按表头列边界
重组单元格；school_report_parser 负责业务字段与统计口径。
"""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

_PAGE_MARKER = "—— 第 {page} 页（OCR 草稿）——\n"
_DPI = 150
_RENDER_TIMEOUT = 120
_OCR_TIMEOUT = 60


class OcrError(RuntimeError):
    pass


def _run(arguments: list[str], *, timeout: int) -> str:
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OcrError(str(exc)) from exc
    if result.returncode != 0:
        raise OcrError(f"tool failed: {arguments[0]}")
    return result.stdout.decode("utf-8", errors="replace")


def _line_words(tsv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with tsv_path.open("r", encoding="utf-8", newline="") as handle:
        # Tesseract TSV 文本可能包含未闭合引号（如将题号 11 误识为 "1），必须禁用引号解析以免吞并后续多行。
        for row in csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row.get("level") != "5" or not (row.get("text") or "").strip():
                continue
            rows.append(
                {
                    "left": int(row["left"]),
                    "top": int(row["top"]),
                    "width": int(row["width"]),
                    "height": int(row["height"]),
                    "block": int(row["block_num"]),
                    "par": int(row["par_num"]),
                    "line": int(row["line_num"]),
                    "text": row["text"].strip(),
                }
            )
    return rows


def _group_lines(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for word in words:
        lines.setdefault((word["block"], word["par"], word["line"]), []).append(word)
    result: list[dict[str, Any]] = []
    for (block, par, line), line_words in lines.items():
        line_words.sort(key=lambda item: item["left"])
        result.append(
            {
                "block": block,
                "par": par,
                "line": line,
                "top": min(item["top"] for item in line_words),
                "left": min(item["left"] for item in line_words),
                "text": " ".join(item["text"] for item in line_words),
                "words": line_words,
            }
        )
    result.sort(key=lambda item: (item["top"], item["left"]))
    return result


def ocr_pdf(data: bytes) -> tuple[list[dict[str, Any]], int]:
    """逐页渲染并逐词 OCR；返回 (按页的文本行列表, 页数)。"""
    with TemporaryDirectory(prefix="pageboy-report-") as directory:
        root = Path(directory)
        pdf = root / "report.pdf"
        pdf.write_bytes(data)
        info = _run(["pdfinfo", str(pdf)], timeout=30)
        pages_line = next((line for line in info.splitlines() if line.startswith("Pages:")), "")
        try:
            page_count = int(pages_line.split(":")[1].strip())
        except (IndexError, ValueError) as exc:
            raise OcrError("pdfinfo pages missing") from exc
        _run(
            ["pdftoppm", "-r", str(_DPI), "-png", "-l", str(page_count), str(pdf), str(root / "page")],
            timeout=_RENDER_TIMEOUT,
        )
        pages: list[dict[str, Any]] = []
        for index in range(1, page_count + 1):
            image = root / f"page-{index:02d}.png"
            if not image.exists():
                image = root / f"page-{index}.png"
            if not image.exists():
                pages.append({"page": index, "lines": []})
                continue
            tsv = root / f"page-{index:02d}.tsv"
            _run(
                ["tesseract", str(image), str(tsv.with_suffix("")), "-l", "chi_sim+eng", "--psm", "6", "tsv"],
                timeout=_OCR_TIMEOUT,
            )
            pages.append({"page": index, "lines": _group_lines(_line_words(tsv))})
        return pages, page_count


def page_text(pages: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for page in pages:
        text = "\n".join(line["text"] for line in page["lines"])
        if text.strip():
            chunks.append(_PAGE_MARKER.format(page=page["page"]) + text)
    return "".join(chunks)


def table_rows(page: dict[str, Any], header_keys: tuple[str, ...]) -> list[dict[str, str | int | float | None]]:
    """按表头词的横向聚类切列；列名按 header_keys 顺序映射。"""
    lines = page["lines"]
    header_line: dict[str, Any] | None = None
    header_index = -1
    for index, line in enumerate(lines):
        joined = "".join(word["text"] for word in line["words"])
        lefts = sorted({word["left"] for word in line["words"]})
        cluster_count = 1 + sum(1 for a, b in zip(lefts, lefts[1:]) if b - a > 60) if lefts else 0
        # 小题表头可能 OCR 成“小是”“mae!”等：用“难度 + 得分率 + 至少 6 列”识别，不用精确词匹配。
        if cluster_count >= len(header_keys) and "难度" in joined and "得分率" in joined:
            header_line = line
            header_index = index
            break
    if header_line is None:
        return []
    lefts = sorted({word["left"] for word in header_line["words"]})
    clusters: list[int] = []
    for left in lefts:
        if not clusters or left - clusters[-1] > 60:
            clusters.append(left)
    if len(clusters) < len(header_keys):
        return []
    boundaries = list(zip(header_keys, clusters[: len(header_keys)]))
    rows: list[dict[str, str | int | float | None]] = []
    for line in lines[header_index + 1 :]:
        text = line["text"].strip()
        if not text or "总结建议" in text:
            continue
        cells: dict[str, str | int | float | None] = {}
        for position, (key, left) in enumerate(boundaries):
            next_left = boundaries[position + 1][1] if position + 1 < len(boundaries) else 10**9
            words = [word["text"] for word in line["words"] if left - 20 <= word["left"] < next_left - 20]
            cells[key] = "".join(words) if words else None
        first = cells.get(boundaries[0][0])
        cleaned_first = str(first or "").strip().strip("\"'“”‘’。·.")
        if not cleaned_first or not re.fullmatch(
            r"(?:\d{1,3}(?:[（(][0-9一二三四五六七八九十]+[）)])?|默写|听力题)", cleaned_first
        ):
            continue
        cells[boundaries[0][0]] = cleaned_first
        rows.append(cells)
    return rows
