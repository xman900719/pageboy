"""学校试卷/答题卡与外部成绩错题的自动化解析、隐私脱敏及 DeepSeek 草稿对齐适配器。

严格守卫边界：
1. 独立于 `guidance.py`（纯业务领域层保持零 I/O、零 HTTP/SDK 依赖）。
2. 所有自动抽取或 AI 初判生成的小题，一律强制标为 `scoring_origin="ocr_draft"` 且
   `confirmed_by_user=False`，绝不绕过人工核对直接进入正式能力证据与错误分析。
3. 发送多模态视觉模型前，默认对含学生姓名/考号的答题卡首页顶部执行本地白色遮罩脱敏。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw

from . import private_files as files
from .guidance import SCHOOL_ERROR_CATEGORIES

# 单次视觉解析最多渲染的页数，兼顾完整试卷覆盖与 DeepSeek 请求体体积安全边界
MAX_VISION_PAGES_PER_ATTACHMENT = 10
HEADER_MASK_RATIO = 0.24
_CORE_SUBJECTS = {"math", "chinese", "english", "physics"}
_VALID_CONFIDENCE = {"high", "medium", "low", "skeleton_only", "external_sync"}
_CONFIDENCE_TO_SOURCE_LABEL = {
    "high": "高置信识别草稿",
    "medium": "中等置信草稿",
    "low": "低置信待人工核对",
    "skeleton_only": "仅原卷题号与分值骨架",
    "external_sync": "外部平台抓取待核对",
}

_SUBJECT_CN = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "physics": "物理",
    "ethics": "道法",
}

# 局部领域高频同义关键词提示（辅助本地无网络骨架匹配 Top-3 候选知识点）
_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    "二次方程": ("一元二次", "求根", "配方法", "判别式", "韦达", "根", "x2", "x²"),
    "二次函数": ("抛物线", "顶点", "对称轴", "y=ax", "开口"),
    "反比例函数": ("反比例", "k/x", "双曲线"),
    "全等": ("△", "平分线", "垂直", "证明", "AC", "AB", "相似"),
    "三角": ("△", "三角形", "勾股", "角度", "斜边", "∠"),
    "几何": ("坐标系", "直线", "线段", "面积", "对称", "旋转", "圆"),
    "概率": ("卡片", "随机", "概率", "统计", "平均"),
    "算术": ("计算", "实数", "绝对值", "根式", "增长率", "不等式"),
    "方程": ("求解", "列方程", "通道", "矩形", "应用题"),
}


class VisionParserConfigError(RuntimeError):
    """视觉/AI 解析配置缺失或格式非法。"""


class VisionParserUnavailableError(RuntimeError):
    """上游 DeepSeek 多模态或文本接口调用失败/超时。"""


@dataclass(frozen=True)
class VisionParserConfig:
    """DeepSeek（及 OpenAI 兼容多模态/文本网关）解析配置。"""

    base_url: str
    api_key: str
    vision_model: str
    text_model: str
    timeout_seconds: float


def load_vision_config(*, require_key: bool = True) -> VisionParserConfig | None:
    """加载视觉与语义解析配置；依次复用 SHUTONG_VISION_* / SHUTONG_AI_* / DEEPSEEK_*，缺失密钥时 Fail-Closed。"""
    base_url = (
        os.getenv("SHUTONG_VISION_BASE_URL")
        or os.getenv("SHUTONG_AI_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com"
    ).strip().rstrip("/")
    # 兼容宿主环境为 Anthropic SDK 配置 DEEPSEEK_BASE_URL=https://.../anthropic 的常见情形
    if base_url.endswith("/anthropic"):
        base_url = base_url[: -len("/anthropic")].rstrip("/") or "https://api.deepseek.com"
    api_key = (
        os.getenv("SHUTONG_VISION_API_KEY")
        or os.getenv("SHUTONG_AI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or ""
    ).strip()
    vision_model = (os.getenv("SHUTONG_VISION_MODEL") or "deepseek-flash").strip() or "deepseek-flash"
    text_model = (
        os.getenv("SHUTONG_TEXT_ENRICH_MODEL")
        or os.getenv("SHUTONG_AI_MODEL")
        or "deepseek-chat"
    ).strip() or "deepseek-chat"
    raw_timeout = (os.getenv("SHUTONG_VISION_TIMEOUT_SECONDS") or "60").strip()
    try:
        timeout_seconds = max(5.0, float(raw_timeout))
    except ValueError:
        timeout_seconds = 60.0

    if not api_key:
        if require_key:
            raise VisionParserConfigError("VISION_PARSER_NOT_CONFIGURED")
        return None
    if not base_url.startswith(("http://", "https://")):
        raise VisionParserConfigError("VISION_BASE_URL_INVALID")
    return VisionParserConfig(
        base_url=base_url,
        api_key=api_key,
        vision_model=vision_model,
        text_model=text_model,
        timeout_seconds=timeout_seconds,
    )


def normalize_question_label(raw: str) -> str:
    """将常见题号规范化为统一格式（如 '1' / '1.' -> '第1题'）。"""
    text = re.sub(r"\s+", "", str(raw or "")).strip("．.、:：")
    if not text:
        return "未命名题"
    m_num = re.fullmatch(r"第?(\d{1,3})题?", text)
    if m_num:
        return f"第{int(m_num.group(1))}题"
    m_sub = re.fullmatch(r"第?(\d{1,3})题?([\(（][^\)）]+[\)）])", text)
    if m_sub:
        sub = m_sub.group(2).replace("（", "(").replace("）", ")")
        return f"第{int(m_sub.group(1))}题{sub}"
    return text[:160]


def _tokenize_chinese_text(text: str) -> set[str]:
    """提取简单稳定的中英文 bigram 与词片用于本地知识点相似度打分。"""
    cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", text or "").lower()
    tokens: set[str] = set()
    for part in cleaned.split():
        if len(part) >= 2:
            tokens.add(part)
        if re.search(r"[\u4e00-\u9fff]", part) and len(part) >= 2:
            for idx in range(len(part) - 1):
                tokens.add(part[idx : idx + 2])
    return tokens


def match_knowledge_candidates(
    snippet: str,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, str]]:
    """基于关键词与发布态知识点目录匹配 Top-N 候选编码（纯本地规则，可作兜底）。"""
    if subject not in _CORE_SUBJECTS:
        return [
            {
                "knowledge_id": "ethics.general",
                "title": "道法综合主题",
                "reason": "道法学科未设独立刷题考点图谱，暂归入综合复盘主题",
            }
        ]
    if not knowledge_catalog:
        return []

    lowered_snippet = (snippet or "").lower()
    snippet_tokens = _tokenize_chinese_text(snippet)
    scored: list[tuple[float, dict[str, Any], list[str]]] = []

    for node in knowledge_catalog:
        code = str(node.get("code") or "")
        name = str(node.get("name") or code)
        desc = str(node.get("description") or "")
        if not code:
            continue
        score = 0.0
        reasons: list[str] = []

        if code.lower() in lowered_snippet or name.lower() in lowered_snippet:
            score += 6.0
            reasons.append(f"直接命中“{name}”")

        node_tokens = _tokenize_chinese_text(f"{name} {desc}")
        overlap = snippet_tokens & node_tokens
        if overlap:
            score += min(4.0, len(overlap) * 0.6)
            reasons.append("题干关键词匹配")

        for anchor, hints in _KEYWORD_HINTS.items():
            if anchor in f"{name} {desc}":
                hit_count = sum(1 for h in hints if h.lower() in lowered_snippet)
                if hit_count:
                    score += hit_count * 1.4
                    reasons.append(f"命中关联特征词({anchor})")

        scored.append((score, node, reasons))

    scored.sort(key=lambda item: (-item[0], str(item[1].get("code") or "")))
    out: list[dict[str, str]] = []
    for sc, node, reasons in scored[:limit]:
        reason_text = "、".join(dict.fromkeys(reasons)) if reasons else "同科核心考点候选"
        if sc <= 0 and out:
            break
        out.append(
            {
                "knowledge_id": str(node["code"]),
                "title": str(node.get("name") or node["code"]),
                "reason": reason_text,
            }
        )
    if not out and knowledge_catalog:
        first = knowledge_catalog[0]
        out.append(
            {
                "knowledge_id": str(first["code"]),
                "title": str(first.get("name") or first["code"]),
                "reason": "未命中明确关键词，默认列出首个学科考点供人工选用",
            }
        )
    return out


def _merge_section_headers(text: str) -> str:
    """仅合并跨行折断的大题题头括号说明（例如 `三、解答题（...\\n...）`），避免误吞选择题括号中的题干。"""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r"^[一二三四五六七八九十]+[、.．]", stripped) and ("（" in stripped or "(" in stripped):
            open_cnt = stripped.count("（") + stripped.count("(")
            close_cnt = stripped.count("）") + stripped.count(")")
            buf = [stripped]
            # 最多向下续拼 3 行闭合大题配分括号说明
            while open_cnt > close_cnt and i + 1 < len(lines) and len(buf) < 4:
                nxt = lines[i + 1].strip()
                if re.match(r"^(?:第\s*)?\d{1,2}\s*[.．、．]", nxt):
                    break
                i += 1
                buf.append(nxt)
                open_cnt += nxt.count("（") + nxt.count("(")
                close_cnt += nxt.count("）") + nxt.count(")")
            out.append(" ".join(buf))
        else:
            out.append(line)
        i += 1
    return "\n".join(out)


def _extract_section_point_map(text: str) -> tuple[dict[int, float], list[tuple[int, float]]]:
    """从中文试卷大题说明文字中抽取“题号 -> 满分”及分节默认每题分值。

    覆盖两类常见声明：
    - `一、选择题（每题 2 分，共 16 分）` -> 节内默认每题 2.0 分
    - `三、解答题（共 68 分，第 17 题 5 分，20-21 题每题 5 分，25-27 题每题各 7 分）` -> 逐题映射
    """
    explicit_points: dict[int, float] = {}
    section_starts: list[tuple[int, float]] = []
    merged_text = _merge_section_headers(text)

    for line_idx, line in enumerate(merged_text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        is_section = bool(re.match(r"^[一二三四五六七八九十]+[、.．]", stripped))
        # 先解析括号/题头内的具体题号或区间分值
        for m in re.finditer(
            r"(?:第\s*)?(\d{1,2})(?:\s*[-–—~至到]\s*(\d{1,2}))?\s*题\s*(?:每题(?:各)?|共)?\s*(\d+(?:\.\d+)?)\s*分",
            stripped,
        ):
            start_n = int(m.group(1))
            end_n = int(m.group(2)) if m.group(2) else start_n
            pts = float(m.group(3))
            if 1 <= start_n <= end_n <= 80 and 0 < pts <= 100:
                # 防止将“共 16 分”误解析为单题 16 分（“每题 2 分”由下文处理）
                if "共" in m.group(0) and start_n != end_n:
                    continue
                for qn in range(start_n, end_n + 1):
                    explicit_points[qn] = pts

        if is_section:
            m_each = re.search(r"每(?:小)?题(?:各)?\s*(\d+(?:\.\d+)?)\s*分", stripped)
            if m_each:
                pts = float(m_each.group(1))
                if 0 < pts <= 100:
                    section_starts.append((line_idx, pts))

    return explicit_points, section_starts


def extract_embedded_text(data: bytes, media_type: str) -> str:
    """仅抽取文件内嵌可机读文字层（PDF pdftotext / DOCX xml），绝不触发慢速全页 OCR。"""
    if media_type == files.DOCX_MEDIA_TYPE:
        return files.extract_docx_text(data).strip()
    if media_type != "application/pdf":
        return ""
    with TemporaryDirectory(prefix="pageboy-txt-") as td:
        root = Path(td)
        pdf_path = root / "doc.pdf"
        out_path = root / "out.txt"
        pdf_path.write_bytes(data)
        files.run_tool(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), str(out_path)])
        text = out_path.read_text(encoding="utf-8", errors="replace")
        if files.pdf_needs_ocr(text):
            return ""
        return text.strip()


def parse_paper_skeleton_from_text(
    text: str,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    *,
    attachment_id: str | None = None,
) -> list[dict[str, Any]]:
    """纯本地从带文字层的试卷正文抽取“题号 + 满分 + 候选知识点”骨架草稿。

    该步骤绝不凭空编造学生得分：一律置 `earned_points=0.0`、`scoring_origin="ocr_draft"`、
    `confirmed_by_user=False`、`draft_confidence="skeleton_only"`，等待人工填分确认。
    """
    if not text or not text.strip():
        return []

    explicit_points, section_starts = _extract_section_point_map(text)
    merged_text = _merge_section_headers(text)
    lines = merged_text.splitlines()

    # 按行追踪当前所属大题默认每题分值
    section_idx = 0
    current_default_pts: float | None = None
    question_blocks: list[tuple[int, list[str]]] = []
    seen_qnums: set[int] = set()
    last_qnum = 0

    for idx, raw_line in enumerate(lines):
        while section_idx < len(section_starts) and idx >= section_starts[section_idx][0]:
            current_default_pts = section_starts[section_idx][1]
            section_idx += 1

        stripped = raw_line.strip()
        if not stripped:
            continue
        # 跳过“数 学，第 1 页，共 6 页”之类页脚和大题标题行
        if re.search(r"第\s*\d+\s*页\s*[，,]?\s*共\s*\d+\s*页", stripped):
            continue
        if re.match(r"^[一二三四五六七八九十]+[、.．]", stripped):
            continue

        m_q = re.match(r"^(?:第\s*)?(\d{1,2})\s*(?:题)?\s*[.．、．]\s*(.*)$", stripped)
        if m_q:
            qnum = int(m_q.group(1))
            rest = m_q.group(2).strip()
            # 防止列表中的年份（如“2026.”）或小序号①/重复编号干扰：要求编号合理且递增
            if 1 <= qnum <= 60 and qnum not in seen_qnums and (last_qnum == 0 or last_qnum < qnum <= last_qnum + 8):
                # 排除类似“18.1”或图片标注“7 题图”之类非题干起始行
                if rest and not rest.startswith("题图"):
                    seen_qnums.add(qnum)
                    last_qnum = qnum
                    question_blocks.append((qnum, [stripped]))
                    continue

        if question_blocks:
            question_blocks[-1][1].append(stripped)

    items: list[dict[str, Any]] = []
    # 需要反查每题所在原始位置对应的大题默认分值
    line_to_default: dict[int, float | None] = {}
    sec_ptr = 0
    cur_def: float | None = None
    for idx in range(len(lines)):
        while sec_ptr < len(section_starts) and idx >= section_starts[sec_ptr][0]:
            cur_def = section_starts[sec_ptr][1]
            sec_ptr += 1
        line_to_default[idx] = cur_def

    for qnum, block_lines in question_blocks:
        snippet = "\n".join(block_lines[:8])
        max_pts = explicit_points.get(qnum)
        if max_pts is None:
            m_stem_pts = re.search(r"(?:本小题满分|满分)\s*(\d+(?:\.\d+)?)\s*分|[（(]\s*(\d+(?:\.\d+)?)\s*分\s*[）)]", snippet)
            if m_stem_pts:
                max_pts = float(m_stem_pts.group(1) or m_stem_pts.group(2))
        if max_pts is None:
            # 查找题号起始行所属大题默认分
            pat = re.compile(rf"^(?:第\s*)?{qnum}\s*(?:题)?\s*[.．、．]")
            for idx, ln in enumerate(lines):
                if pat.match(ln.strip()):
                    max_pts = line_to_default.get(idx)
                    break
        if max_pts is None or not (0 < max_pts <= 100):
            max_pts = 2.0

        candidates = match_knowledge_candidates(snippet, subject, knowledge_catalog, limit=3)
        primary_kid = candidates[0]["knowledge_id"] if candidates else ("ethics.general" if subject not in _CORE_SUBJECTS else "unmapped")
        items.append(
            {
                "question_label": f"第{qnum}题",
                "knowledge_id": primary_kid,
                "earned_points": 0.0,
                "max_points": round(float(max_pts), 2),
                "scoring_origin": "ocr_draft",
                "confirmed_by_user": False,
                "error_category": None,
                "error_note": None,
                "draft_source_attachment_id": attachment_id,
                "draft_confidence": "skeleton_only",
                "draft_reason": f"从原卷文字层提取题号与分值（满分 {max_pts:g} 分），暂未读取作答得分，请人工填写实得分后确认。",
                "draft_knowledge_candidates": candidates,
                "stem": snippet[:500],
            }
        )
    return items


def _looks_like_answer_sheet(filename: str, data: bytes, first_page_path: Path | None = None) -> bool:
    """判断附件是否属于含学生姓名/考号栏位的答题卡扫描件，触发首页顶部脱敏。"""
    lowered = (filename or "").lower()
    if any(kw in lowered for kw in ("答", "卡", "answer", "card", "sheet")):
        return True
    # 若文件名不明确且存在渲染页图，可快速用 tesseract 检查顶部 26% 是否出现“姓名/考场/座位”
    if first_page_path is not None and first_page_path.exists():
        try:
            with Image.open(first_page_path) as im:
                w, h = im.size
                top_strip = im.crop((0, 0, w, max(1, int(h * 0.28))))
                with TemporaryDirectory(prefix="pageboy-hdr-") as td:
                    hdr_png = Path(td) / "hdr.png"
                    top_strip.save(hdr_png, format="PNG")
                    res = subprocess.run(
                        ["tesseract", str(hdr_png), "stdout", "-l", "chi_sim+eng"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    header_txt = res.stdout or ""
                    if any(k in header_txt for k in ("姓名", "考场", "座位", "准考证", "答题卡")):
                        return True
        except Exception:
            pass
    return False


def mask_top_student_header(png_bytes: bytes, ratio: float = HEADER_MASK_RATIO) -> bytes:
    """将图片顶部指定比例（默认 24%）遮白脱敏，用于屏蔽学生姓名、班级与座位号 PII。"""
    clamped_ratio = max(0.05, min(0.5, float(ratio)))
    with Image.open(BytesIO(png_bytes)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        mask_h = max(1, int(h * clamped_ratio))
        draw = ImageDraw.Draw(rgb)
        draw.rectangle([(0, 0), (w, mask_h)], fill=(255, 255, 255))
        buf = BytesIO()
        rgb.save(buf, format="PNG")
        return buf.getvalue()


def render_masked_pages_for_vision(
    attachments: list[dict[str, Any]],
    *,
    mask_student_header: bool = True,
    max_pages_per_file: int = MAX_VISION_PAGES_PER_ATTACHMENT,
) -> list[dict[str, Any]]:
    """将校考 PDF/图片附件转为可安全外发 DeepSeek 视觉模型的脱敏 PNG 帧列表。"""
    rendered: list[dict[str, Any]] = []
    for att in attachments:
        att_id = str(att["id"])
        filename = str(att["filename"])
        media_type = str(att["media_type"])
        data = bytes(att["data"])

        if media_type in ("image/png", "image/jpeg"):
            with Image.open(BytesIO(data)) as im:
                buf = BytesIO()
                im.convert("RGB").save(buf, format="PNG")
                raw_png = buf.getvalue()
            is_sheet = _looks_like_answer_sheet(filename, data)
            masked = False
            if mask_student_header and is_sheet:
                raw_png = mask_top_student_header(raw_png)
                masked = True
            rendered.append(
                {
                    "attachment_id": att_id,
                    "filename": filename,
                    "page": 1,
                    "masked_header": masked,
                    "data_url": "data:image/png;base64," + base64.b64encode(raw_png).decode("ascii"),
                }
            )
            continue

        if media_type != "application/pdf":
            continue

        with TemporaryDirectory(prefix="pageboy-vis-") as td:
            root = Path(td)
            pdf_path = root / "doc.pdf"
            pdf_path.write_bytes(data)
            files.run_tool(
                [
                    "pdftoppm",
                    "-r",
                    str(files.PDF_RENDER_DPI),
                    "-png",
                    "-l",
                    str(max(1, min(files.MAX_PAGES, max_pages_per_file))),
                    str(pdf_path),
                    str(root / "page"),
                ],
                timeout=files.PDF_RENDER_TIMEOUT,
            )
            page_files = sorted(root.glob("page-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
            if not page_files:
                continue
            is_sheet = _looks_like_answer_sheet(filename, data, first_page_path=page_files[0])
            for page_idx, page_file in enumerate(page_files, 1):
                png_bytes = page_file.read_bytes()
                masked = False
                if mask_student_header and page_idx == 1 and is_sheet:
                    png_bytes = mask_top_student_header(png_bytes)
                    masked = True
                rendered.append(
                    {
                        "attachment_id": att_id,
                        "filename": filename,
                        "page": page_idx,
                        "masked_header": masked,
                        "data_url": "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii"),
                    }
                )
    return rendered


def _open_httpx_client(timeout_seconds: float, *, trust_env: bool) -> httpx.Client:
    """构造 httpx 客户端；宿主机若开启 socks5 全局代理但缺 socksio 则回退直连上游。"""
    try:
        return httpx.Client(timeout=timeout_seconds, trust_env=trust_env)
    except ImportError:
        return httpx.Client(timeout=timeout_seconds, trust_env=False)


def _post_deepseek_json(
    cfg: VisionParserConfig,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 8192,
) -> dict[str, Any]:
    """向 DeepSeek / OpenAI 兼容端点发送结构化 JSON 请求并做统一错误处理。"""
    endpoint = f"{cfg.base_url}/chat/completions" if cfg.base_url.endswith("/v1") else f"{cfg.base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    is_loopback = (urlparse(endpoint).hostname or "") in {"127.0.0.1", "localhost", "::1"}
    try:
        with _open_httpx_client(cfg.timeout_seconds, trust_env=not is_loopback) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.TimeoutException as exc:
        raise VisionParserUnavailableError("VISION_PARSER_TIMEOUT") from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        raise VisionParserUnavailableError(f"VISION_PARSER_HTTP_{code}") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise VisionParserUnavailableError("VISION_PARSER_UNAVAILABLE") from exc

    try:
        choices = body.get("choices") or []
        content = ((choices[0] or {}).get("message") or {}).get("content") or ""
        if not content.strip():
            raise ValueError("empty json content")
        return json.loads(content)
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        raise VisionParserUnavailableError("VISION_PARSER_INVALID_JSON") from exc


def _normalize_ai_draft_items(
    raw_items: Any,
    *,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    default_attachment_id: str | None = None,
    default_confidence: str = "medium",
) -> list[dict[str, Any]]:
    """对模型返回的小题草稿执行严格白名单、分值钳位与未确认门禁归一化。"""
    if not isinstance(raw_items, list):
        return []
    valid_codes = {str(n["code"]): str(n.get("name") or n["code"]) for n in knowledge_catalog if n.get("code")}
    normalized: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        label = normalize_question_label(str(entry.get("question_label") or entry.get("label") or ""))
        if not label or label == "未命名题" or label in seen_labels:
            continue
        seen_labels.add(label)

        try:
            max_pts = float(entry.get("max_points") or 0)
        except (TypeError, ValueError):
            max_pts = 0.0
        if not (0 < max_pts <= 100):
            max_pts = 2.0
        max_pts = round(max_pts, 2)

        raw_earned = entry.get("draft_earned_points", entry.get("earned_points"))
        try:
            earned_pts = float(raw_earned) if raw_earned is not None else 0.0
        except (TypeError, ValueError):
            earned_pts = 0.0
        earned_pts = round(max(0.0, min(max_pts, earned_pts)), 2)

        raw_kid = str(entry.get("knowledge_id") or "").strip()
        stem_hint = str(entry.get("stem_summary") or entry.get("reason") or entry.get("error_note") or label)
        fallback_candidates = match_knowledge_candidates(stem_hint, subject, knowledge_catalog, limit=3)

        if subject not in _CORE_SUBJECTS:
            final_kid = raw_kid if raw_kid and len(raw_kid) <= 100 else "ethics.general"
            candidates = [{"knowledge_id": final_kid, "title": "道法综合主题" if final_kid == "ethics.general" else final_kid, "reason": "非核心刷题学科复盘主题"}]
        elif raw_kid in valid_codes:
            final_kid = raw_kid
            candidates = [{"knowledge_id": raw_kid, "title": valid_codes[raw_kid], "reason": "视觉模型直接匹配课标编码"}]
            for cand in fallback_candidates:
                if cand["knowledge_id"] != raw_kid and len(candidates) < 3:
                    candidates.append(cand)
        else:
            final_kid = fallback_candidates[0]["knowledge_id"] if fallback_candidates else (next(iter(valid_codes), "unmapped"))
            candidates = fallback_candidates

        conf = str(entry.get("confidence") or entry.get("draft_confidence") or default_confidence).strip().lower()
        if conf not in _VALID_CONFIDENCE:
            conf = default_confidence

        raw_cat = entry.get("error_category")
        err_cat = raw_cat if (earned_pts < max_pts and raw_cat in SCHOOL_ERROR_CATEGORIES) else None
        raw_note = entry.get("error_note")
        err_note = str(raw_note).strip()[:500] or None if (earned_pts < max_pts and raw_note) else None
        reason = str(entry.get("reason") or entry.get("draft_reason") or _CONFIDENCE_TO_SOURCE_LABEL.get(conf, "待核对草稿")).strip()[:500]

        normalized.append(
            {
                "question_label": label,
                "knowledge_id": final_kid,
                "earned_points": earned_pts,
                "max_points": max_pts,
                "scoring_origin": "ocr_draft",
                "confirmed_by_user": False,
                "error_category": err_cat,
                "error_note": err_note,
                "draft_source_attachment_id": default_attachment_id,
                "draft_confidence": conf,
                "draft_reason": reason,
                "draft_knowledge_candidates": candidates,
            }
        )
    return normalized


def parse_items_with_deepseek_vision(
    *,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    mask_student_header: bool = True,
    cfg: VisionParserConfig | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """使用 DeepSeek 多模态视觉模型（deepseek-flash）联合解析原卷与答题卡为 ocr_draft 草稿。"""
    resolved_cfg = cfg or load_vision_config(require_key=True)
    assert resolved_cfg is not None

    frames = render_masked_pages_for_vision(attachments, mask_student_header=mask_student_header)
    if not frames:
        return [], {"pages_sent": 0, "masked_pages": 0, "model": resolved_cfg.vision_model}

    subject_cn = _SUBJECT_CN.get(subject, subject)
    if subject in _CORE_SUBJECTS and knowledge_catalog:
        catalog_lines = "\n".join(f"- {n['code']} : {n.get('name', n['code'])}" for n in knowledge_catalog[:120])
        kid_rule = f"knowledge_id 必须严格从以下已发布{subject_cn}课标编码中择一填写：\n{catalog_lines}"
    else:
        kid_rule = "当前科目未启用标准刷题知识点编码，请将 knowledge_id 填为 'ethics.general' 或简洁中文主题词。"

    prompt_text = (
        f"你是严谨的初中教研辅助助手。请逐页查看上传的【{subject_cn}】学校考试原卷与（或）学生答题卡图像，"
        "抽取出每一道独立小题的结构化草稿 JSON，供家长在界面中核对实得分与错因。\n"
        "【硬性纪律】\n"
        "1. 仅输出严格 JSON 对象，格式为 {\"items\": [...]}，每项包含：\n"
        "   - question_label: 字符串，格式如 \"第1题\"、\"第18题\"\n"
        "   - max_points: 数字，该题满分（如 2、4、6、8），依据卷面大题/小题配分推断\n"
        "   - draft_earned_points: 数字（范围 0 到 max_points）。**如果图上能看清老师批改扣分（如 -1/-2）或对错钩叉且能算出得分，请填写推算得分并将 confidence 设为 high/medium；如果图上完全看不到批改分数或无法确定主观作答得分，严禁胡编高分，请填 0 并将 confidence 设为 'low'，同时在 reason 中诚实写明“纸面无明确评分标记，请家长人工填分”。**\n"
        "   - knowledge_id: 最匹配的考点编码\n"
        "   - error_category: 仅当 draft_earned_points < max_points 时从 [\"concept\", \"calculation\", \"reading\", \"method\", \"norm\", \"other\"] 中猜测最可能一项，否则填 null\n"
        "   - error_note: 仅当发现明确错点线索时给简短复盘草稿（50 字内），否则 null\n"
        "   - confidence: \"high\" | \"medium\" | \"low\"\n"
        "   - reason: 简述判断依据（例如“原卷二大题每题2分；答题卡涂选B；纸面左缘标-1”）\n"
        f"2. {kid_rule}\n"
        "3. 严禁虚构不存在的题号或预测总分。\n"
    )

    content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
    for frame in frames:
        content_parts.append(
            {
                "type": "text",
                "text": f"[附件 {frame['filename']} 第 {frame['page']} 页{'（顶部已脱敏）' if frame['masked_header'] else ''}]",
            }
        )
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": frame["data_url"], "detail": "high"},
            }
        )

    parsed_json = _post_deepseek_json(
        resolved_cfg,
        model=resolved_cfg.vision_model,
        messages=[
            {"role": "system", "content": "你只输出符合要求的严格 JSON 对象，绝不附带 Markdown 代码块或多余文字。"},
            {"role": "user", "content": content_parts},
        ],
    )
    default_att_id = str(attachments[0]["id"]) if attachments else None
    items = _normalize_ai_draft_items(
        parsed_json.get("items"),
        subject=subject,
        knowledge_catalog=knowledge_catalog,
        default_attachment_id=default_att_id,
        default_confidence="medium",
    )
    meta = {
        "pages_sent": len(frames),
        "masked_pages": sum(1 for f in frames if f["masked_header"]),
        "model": resolved_cfg.vision_model,
    }
    return items, meta


def enrich_external_items_with_deepseek(
    *,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    external_items: list[dict[str, Any]],
    use_ai: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """为外部平台（如 k12100.com）抓取的逐题得分与错题信息补全课标考点与错因草稿。

    即使未配置 DeepSeek API Key，也会优雅回退至本地关键词匹配，不阻断客观成绩导入。
    """
    if not external_items:
        return [], "none"

    cfg = load_vision_config(require_key=False) if use_ai else None
    subject_cn = _SUBJECT_CN.get(subject, subject)

    if cfg is not None:
        try:
            catalog_lines = (
                "\n".join(f"- {n['code']} : {n.get('name', n['code'])}" for n in knowledge_catalog[:120])
                if (subject in _CORE_SUBJECTS and knowledge_catalog)
                else "- ethics.general : 道法综合主题"
            )
            sanitized_rows = [
                {
                    "question_label": normalize_question_label(str(row.get("question_label") or "")),
                    "earned_points": float(row.get("earned_points") or 0.0),
                    "max_points": float(row.get("max_points") or 2.0),
                    "stem_text": str(row.get("stem_text") or "")[:400],
                    "wrong_reason": str(row.get("wrong_reason") or "")[:200],
                }
                for row in external_items
            ]
            # 大题量试卷（如英语 58 题）按每批 18 题分批请求，避免单次 JSON 输出触及 4096 token 上限被截断。
            batch_size = 18
            ai_by_label: dict[str, dict[str, Any]] = {}
            for start in range(0, len(sanitized_rows), batch_size):
                batch_rows = sanitized_rows[start : start + batch_size]
                prompt = (
                    f"请为以下来自校考成绩平台的【{subject_cn}】逐题记录匹配课标考点与错因建议。\n"
                    "必须输出严格 JSON 对象 {\"items\": [...]}，保留每题原 question_label 与分数，"
                    "补充 knowledge_id（必须选自下方列表）、error_category（仅当 earned_points < max_points 时选 "
                    "[\"concept\", \"calculation\", \"reading\", \"method\", \"norm\", \"other\"] 之一，否则 null）、"
                    "error_note（失分复盘建议 60 字内，满分题填 null）与 reason（匹配理由）。\n"
                    f"合法考点列表：\n{catalog_lines}\n\n待对齐明细：\n{json.dumps(batch_rows, ensure_ascii=False)}"
                )
                data = _post_deepseek_json(
                    cfg,
                    model=cfg.text_model,
                    messages=[
                        {"role": "system", "content": "你是初中教学知识点标注助手，只输出严格 JSON 对象。"},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=4096,
                )
                for row in data.get("items") or []:
                    if not isinstance(row, dict):
                        continue
                    ai_lbl = normalize_question_label(str(row.get("question_label") or ""))
                    if ai_lbl:
                        ai_by_label[ai_lbl] = row
            merged: list[dict[str, Any]] = []
            for row in sanitized_rows:
                lbl = row["question_label"]
                ai_row = ai_by_label.get(lbl, {})
                merged.append(
                    {
                        "question_label": lbl,
                        "earned_points": row["earned_points"],
                        "max_points": row["max_points"],
                        "knowledge_id": ai_row.get("knowledge_id"),
                        "error_category": ai_row.get("error_category"),
                        "error_note": ai_row.get("error_note") or (row["wrong_reason"] or None),
                        "confidence": "external_sync",
                        "reason": str(ai_row.get("reason") or "来源平台真实分值 + DeepSeek 考点与错因匹配（待核对）"),
                        "stem_summary": f"{row['stem_text']} {row['wrong_reason']}".strip(),
                    }
                )
            return (
                _normalize_ai_draft_items(
                    merged,
                    subject=subject,
                    knowledge_catalog=knowledge_catalog,
                    default_confidence="external_sync",
                ),
                f"external_plus_{cfg.text_model}",
            )
        except VisionParserUnavailableError:
            pass

    # 无 API Key 或上游短暂异常时的本地关键词降级路径（完整保留平台真实分数）
    fallback_rows = []
    for row in external_items:
        lbl = normalize_question_label(str(row.get("question_label") or ""))
        earned = float(row.get("earned_points") or 0.0)
        max_pts = float(row.get("max_points") or 2.0)
        hint_txt = f"{row.get('stem_text') or ''} {row.get('wrong_reason') or ''}".strip()
        fallback_rows.append(
            {
                "question_label": lbl,
                "earned_points": earned,
                "max_points": max_pts,
                "knowledge_id": row.get("knowledge_id"),
                "error_category": row.get("error_category") if earned < max_pts else None,
                "error_note": (row.get("wrong_reason") or None) if earned < max_pts else None,
                "confidence": "external_sync",
                "reason": "来源平台实得分数 + 本地关键词候选考点（未调用 AI，待人工核对）",
                "stem_summary": hint_txt or lbl,
            }
        )
    return (
        _normalize_ai_draft_items(
            fallback_rows,
            subject=subject,
            knowledge_catalog=knowledge_catalog,
            default_confidence="external_sync",
        ),
        "external_local_rules",
    )
