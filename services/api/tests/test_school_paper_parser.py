"""校考文档自动解析适配器（本地规则骨架 + DeepSeek 视觉/语义对齐 + PII 顶部遮罩）单测。"""

from __future__ import annotations

from io import BytesIO
import json

from PIL import Image, ImageDraw
import pytest

from shutong import school_paper_parser as parser


_MATH_CATALOG = [
    {"code": "math.eq.quadratic", "name": "一元二次方程", "description": "配方法、求根公式、根的判别式与韦达定理"},
    {"code": "math.func.quadratic", "name": "二次函数", "description": "抛物线顶点坐标、对称轴与最值"},
    {"code": "math.func.inverse", "name": "反比例函数", "description": "反比例函数图象与性质"},
    {"code": "math.geo.triangle", "name": "三角形与几何证明", "description": "角平分线、全等三角形与坐标综合"},
]


def test_parse_paper_skeleton_extracts_sections_and_sum():
    """真实十月数学卷版式（含跨行解答题分值说明）应准确抽取全部题号与满分，且得分默认为 0 草稿。"""
    sample = """
清华附中朝阳学校 九年级统一练习 数 学
一、选择题（每题 2 分，共 16 分）
1. 一元二次方程 3x^2 - 4x - 1 = 0 的常数项是（ ）
2. 抛物线 y = (x-1)^2 + 2 的顶点坐标是（ ）
8. 在平面直角坐标系中，抛物线平移问题。
二、填空题（每题 2 分，共 16 分）
9. 若 sqrt(3x-3) 在实数范围内有意义。
12. 反比例函数 y=6/x 的图象经过点 A。
三、解答题（共 68 分，第 17 题 5 分，第 18 题 8 分，19 题 6 分，20-21 题每题 5 分，
22-24 题每题 6 分，25-27 题每题各 7 分）
17. 计算实数混合运算。
18. 解一元二次方程：x^2 - 6x = 7。
19. 已知二次函数 y = x^2 - 6x + 5，求顶点坐标。
20. 已知关于 x 的一元二次方程有实数根。
22. 矩形绿地应用题，列方程求解。
23. 反比例函数面积问题。
25. 抛物线对称轴综合。
26. 已知△ABC 中 AD 是角平分线，求证线段关系。
"""
    items = parser.parse_paper_skeleton_from_text(sample, "math", _MATH_CATALOG, attachment_id="att-1")
    by_label = {it["question_label"]: it for it in items}

    assert by_label["第1题"]["max_points"] == 2.0
    assert by_label["第1题"]["knowledge_id"] == "math.eq.quadratic"
    assert by_label["第2题"]["knowledge_id"] == "math.func.quadratic"
    assert by_label["第9题"]["max_points"] == 2.0
    assert by_label["第12题"]["knowledge_id"] == "math.func.inverse"
    assert by_label["第17题"]["max_points"] == 5.0
    assert by_label["第18题"]["max_points"] == 8.0
    assert by_label["第19题"]["max_points"] == 6.0
    assert by_label["第20题"]["max_points"] == 5.0
    assert by_label["第22题"]["max_points"] == 6.0
    assert by_label["第25题"]["max_points"] == 7.0
    assert by_label["第26题"]["max_points"] == 7.0
    assert by_label["第26题"]["knowledge_id"] == "math.geo.triangle"

    # 骨架模式绝不猜分：全员草稿未确认且得分默认为 0
    for it in items:
        assert it["scoring_origin"] == "ocr_draft"
        assert it["confirmed_by_user"] is False
        assert it["earned_points"] == 0.0
        assert it["draft_confidence"] == "skeleton_only"
        assert it["draft_source_attachment_id"] == "att-1"
        assert len(it["draft_knowledge_candidates"]) >= 1


def test_parse_paper_skeleton_ethics_uses_general_topic():
    sample = "一、判断与简答题（每题 4 分，共 8 分）\n1. 材料体现法治精神。\n2. 简述创新驱动意义。"
    items = parser.parse_paper_skeleton_from_text(sample, "ethics", [])
    assert len(items) == 2
    assert all(it["knowledge_id"] == "ethics.general" for it in items)
    assert all(it["max_points"] == 4.0 for it in items)


def test_mask_top_student_header_blanks_pii_and_preserves_body():
    """顶部 24% 姓名/考号区域涂白，正文解答笔迹区域保持原像素不变。"""
    img = Image.new("RGB", (400, 500), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    # 顶部（y=30..70）绘制模拟姓名黑字；中下部（y=260..320）绘制模拟解答笔迹
    draw.rectangle([(20, 30), (200, 70)], fill=(10, 10, 10))
    draw.rectangle([(40, 260), (240, 320)], fill=(20, 20, 20))
    raw = BytesIO()
    img.save(raw, format="PNG")

    masked_bytes = parser.mask_top_student_header(raw.getvalue(), ratio=0.24)
    with Image.open(BytesIO(masked_bytes)) as out:
        assert out.getpixel((100, 50)) == (255, 255, 255)
        assert out.getpixel((100, 280)) == (20, 20, 20)

    rendered = parser.render_masked_pages_for_vision(
        [{"id": "att-sheet", "filename": "数学答题卡.png", "media_type": "image/png", "data": raw.getvalue()}],
        mask_student_header=True,
    )
    assert len(rendered) == 1
    assert rendered[0]["masked_header"] is True
    assert rendered[0]["data_url"].startswith("data:image/png;base64,")


def test_load_vision_config_fails_closed_when_missing(monkeypatch):
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(parser.VisionParserConfigError, match="VISION_PARSER_NOT_CONFIGURED"):
        parser.load_vision_config(require_key=True)
    assert parser.load_vision_config(require_key=False) is None

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-fallback")
    cfg_ds = parser.load_vision_config(require_key=True)
    assert cfg_ds is not None and cfg_ds.api_key == "sk-deepseek-fallback"

    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test-reuse")
    cfg = parser.load_vision_config(require_key=True)
    assert cfg is not None
    assert cfg.api_key == "sk-test-reuse"
    assert cfg.vision_model == "deepseek-flash"
    assert cfg.text_model == "deepseek-chat"


def test_parse_items_with_deepseek_vision_enforces_guardrails(monkeypatch):
    """验证调用 deepseek-flash、分值越界钳位、非法编码回退白名单及强制未确认草稿。"""
    captured = {}

    def fake_post(cfg, *, model, messages, max_tokens=8192):
        captured["model"] = model
        captured["messages"] = messages
        return {
            "items": [
                {
                    "question_label": "1",
                    "max_points": 2,
                    "draft_earned_points": 99,  # 故意超界 -> 钳位到 2.0 且抹去 error_category
                    "knowledge_id": "math.eq.quadratic",
                    "error_category": "calculation",
                    "confidence": "high",
                    "reason": "客观题涂卡清晰",
                },
                {
                    "question_label": "第18题",
                    "max_points": 8,
                    "draft_earned_points": 5,
                    "knowledge_id": "math.fabricated.code",  # 故意编造非法编码 -> 回退白名单
                    "stem_summary": "解一元二次方程移项",
                    "error_category": "calculation",
                    "error_note": "符号移项出错",
                    "confidence": "medium",
                    "reason": "答题卡旁可见扣3分",
                },
            ]
        }

    monkeypatch.setattr(parser, "_post_deepseek_json", fake_post)
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")

    cfg = parser.VisionParserConfig(
        base_url="https://api.deepseek.com",
        api_key="sk-fake",
        vision_model="deepseek-flash",
        text_model="deepseek-chat",
        timeout_seconds=30.0,
    )
    items, meta = parser.parse_items_with_deepseek_vision(
        subject="math",
        knowledge_catalog=_MATH_CATALOG,
        attachments=[{"id": "att-a", "filename": "数学答.png", "media_type": "image/png", "data": buf.getvalue()}],
        mask_student_header=True,
        cfg=cfg,
    )

    assert captured["model"] == "deepseek-flash"
    assert meta["pages_sent"] == 1
    assert meta["masked_pages"] == 1
    assert len(items) == 2

    q1, q18 = items[0], items[1]
    assert q1["question_label"] == "第1题"
    assert q1["earned_points"] == 2.0  # 99 钳位至满分 2.0
    assert q1["error_category"] is None  # 满分题不得带错因
    assert q1["scoring_origin"] == "ocr_draft"
    assert q1["confirmed_by_user"] is False

    assert q18["question_label"] == "第18题"
    assert q18["knowledge_id"] in {n["code"] for n in _MATH_CATALOG}
    assert q18["knowledge_id"] == "math.eq.quadratic"
    assert q18["error_category"] == "calculation"
    assert q18["error_note"] == "符号移项出错"
    assert q18["scoring_origin"] == "ocr_draft"
    assert q18["confirmed_by_user"] is False


def test_enrich_external_items_fallback_without_key_and_with_deepseek(monkeypatch):
    """无密钥降级本地规则匹配，有密钥时调用 deepseek-chat 补全错因且保持实得分数。"""
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    ext = [
        {"question_label": "19", "earned_points": 3, "max_points": 6, "stem_text": "抛物线顶点坐标", "wrong_reason": "顶点纵坐标算错"}
    ]
    rows_local, mode_local = parser.enrich_external_items_with_deepseek(
        subject="math", knowledge_catalog=_MATH_CATALOG, external_items=ext, use_ai=True
    )
    assert mode_local == "external_local_rules"
    assert rows_local[0]["question_label"] == "第19题"
    assert rows_local[0]["earned_points"] == 3.0
    assert rows_local[0]["knowledge_id"] == "math.func.quadratic"
    assert rows_local[0]["confirmed_by_user"] is False

    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test")
    monkeypatch.setattr(
        parser,
        "_post_deepseek_json",
        lambda cfg, **kw: {
            "items": [
                {
                    "question_label": "第19题",
                    "knowledge_id": "math.func.quadratic",
                    "error_category": "calculation",
                    "error_note": "配方法常数项计算出错",
                    "reason": "由 DeepSeek 对齐课标知识点",
                }
            ]
        },
    )
    rows_ai, mode_ai = parser.enrich_external_items_with_deepseek(
        subject="math", knowledge_catalog=_MATH_CATALOG, external_items=ext, use_ai=True
    )
    assert mode_ai == "external_plus_deepseek-chat"
    assert rows_ai[0]["earned_points"] == 3.0
    assert rows_ai[0]["error_category"] == "calculation"
    assert rows_ai[0]["error_note"] == "配方法常数项计算出错"
    assert rows_ai[0]["scoring_origin"] == "ocr_draft"
    assert rows_ai[0]["confirmed_by_user"] is False
