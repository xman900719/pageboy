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


def test_enrich_external_items_chunks_large_exam_batches(monkeypatch):
    """超过 18 题的大题量试卷自动分批调用 DeepSeek 并聚合全部草稿结果。"""
    import json

    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test")
    batch_sizes: list[int] = []

    def fake_post(cfg, **kw):
        # 从 prompt 末尾 JSON 解析本批题目并回传对应标注
        user_msg = kw["messages"][-1]["content"]
        payload_text = user_msg.split("待对齐明细：\n", 1)[1]
        batch_rows = json.loads(payload_text)
        batch_sizes.append(len(batch_rows))
        return {
            "items": [
                {
                    "question_label": row["question_label"],
                    "knowledge_id": "math.eq.quadratic",
                    "error_category": "method" if row["earned_points"] < row["max_points"] else None,
                    "error_note": f"{row['question_label']}批注" if row["earned_points"] < row["max_points"] else None,
                    "reason": "分批对齐验证",
                }
                for row in batch_rows
            ]
        }

    monkeypatch.setattr(parser, "_post_deepseek_json", fake_post)
    ext = [
        {
            "question_label": str(idx),
            "earned_points": 1.0 if idx % 2 else 2.0,
            "max_points": 2.0,
            "stem_text": f"测试题干 {idx}",
            "wrong_reason": "思路偏差" if idx % 2 else "",
        }
        for idx in range(1, 26)
    ]

    rows, mode = parser.enrich_external_items_with_deepseek(
        subject="math",
        knowledge_catalog=_MATH_CATALOG,
        external_items=ext,
        use_ai=True,
    )
    assert mode == "external_plus_deepseek-chat"
    assert batch_sizes == [18, 7]
    assert len(rows) == 25
    assert rows[0]["error_category"] == "method"
    assert rows[0]["error_note"] == "第1题批注"
    assert rows[1]["error_category"] is None
    assert rows[-1]["question_label"] == "第25题"
    assert rows[-1]["error_category"] == "method"
    assert all(row["scoring_origin"] == "ocr_draft" and row["confirmed_by_user"] is False for row in rows)


def test_load_vision_config_strips_anthropic_suffix(monkeypatch):
    """宿主 Shell 若设置 DEEPSEEK_BASE_URL=.../anthropic，自动归一为 OpenAI 兼容根地址。"""
    monkeypatch.delenv("SHUTONG_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("SHUTONG_AI_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic/")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    cfg = parser.load_vision_config(require_key=True)
    assert cfg is not None
    assert cfg.base_url == "https://api.deepseek.com"


def test_auto_associate_five_subjects_and_top3_guarantee(monkeypatch):
    """覆盖 5 学科 Tier 1 关键词命中与 Tier 3 先验补齐，保证每题均产出 3 个有效候选。"""
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    chinese_catalog = [
        {"code": "chinese_cand.base.phonetics", "name": "字音辨析", "is_elective": False},
        {"code": "chinese_cand.base.character_orthography", "name": "字形书写", "is_elective": False},
        {"code": "chinese_cand.base.idiom_vocabulary", "name": "词语与成语运用", "is_elective": False},
        {"code": "chinese_cand.poetry.dictation", "name": "古诗文名句默写", "is_elective": False},
    ]
    english_catalog = [
        {"code": "english_cand.pronoun.types", "name": "代词", "is_elective": False},
        {"code": "english_cand.tense.present_perfect", "name": "现在完成时", "is_elective": False},
        {"code": "english_cand.syntax.object_clause", "name": "宾语从句", "is_elective": False},
        {"code": "english_cand.reading.facts_inference", "name": "阅读理解", "is_elective": False},
    ]
    physics_catalog = [
        {"code": "physics_cand.light.propagate_reflect", "name": "光传播与反射", "is_elective": False},
        {"code": "physics_cand.force.buoyancy", "name": "浮力", "is_elective": False},
        {"code": "physics_cand.energy.ohm_law", "name": "欧姆定律", "is_elective": False},
        {"code": "physics_cand.exp.inquiry_methods", "name": "实验探究方法", "is_elective": False},
    ]

    math_assoc = parser.auto_associate_school_items(
        subject="math",
        knowledge_catalog=_MATH_CATALOG,
        items=[
            {"question_label": "第1题", "question_type": "单选题", "max_points": 2.0, "stem_text": "下列抛物线顶点对称轴正确的是"},
            {"question_label": "第10题", "question_type": "填空题", "max_points": 2.0, "stem_text": ""},
        ],
        use_ai=False,
    )
    assert math_assoc[0]["knowledge_id"] == "math.func.quadratic"
    assert math_assoc[0]["draft_confidence"] == "auto_matched"
    assert len(math_assoc[0]["draft_knowledge_candidates"]) == 3
    assert math_assoc[1]["draft_confidence"] == "type_inferred"
    assert len(math_assoc[1]["draft_knowledge_candidates"]) == 3

    cn_assoc = parser.auto_associate_school_items(
        subject="chinese",
        knowledge_catalog=chinese_catalog,
        items=[{"question_label": "第7题", "question_type": "默写", "max_points": 6.0, "stem_text": "古诗文默写补全"}],
        use_ai=False,
    )
    assert cn_assoc[0]["knowledge_id"] == "chinese_cand.poetry.dictation"
    assert len(cn_assoc[0]["draft_knowledge_candidates"]) == 3

    en_assoc = parser.auto_associate_school_items(
        subject="english",
        knowledge_catalog=english_catalog,
        items=[{"question_label": "第11题", "question_type": "单项选择", "max_points": 1.0, "stem_text": ""}],
        use_ai=False,
    )
    assert en_assoc[0]["knowledge_id"] == "english_cand.syntax.object_clause"
    assert len(en_assoc[0]["draft_knowledge_candidates"]) == 3

    phy_assoc = parser.auto_associate_school_items(
        subject="physics",
        knowledge_catalog=physics_catalog,
        items=[{"question_label": "第14题", "question_type": "多选题", "max_points": 2.0, "stem_text": ""}],
        use_ai=False,
    )
    assert phy_assoc[0]["knowledge_id"] == "physics_cand.force.buoyancy"
    assert len(phy_assoc[0]["draft_knowledge_candidates"]) == 3

    eth_assoc = parser.auto_associate_school_items(
        subject="ethics",
        knowledge_catalog=[],
        items=[{"question_label": "第18题", "question_type": "材料分析", "max_points": 8.0, "stem_text": ""}],
        use_ai=False,
    )
    assert eth_assoc[0]["knowledge_id"] == "ethics.general"
    assert [c["knowledge_id"] for c in eth_assoc[0]["draft_knowledge_candidates"]] == [
        "ethics.general",
        "ethics.law_citizenship",
        "ethics.national_values",
    ]


def test_auto_associate_tier2_ai_and_unavailable_fallback(monkeypatch):
    """未强命中本地关键词的有题干题目触发 Tier 2 DeepSeek 语义匹配；上游不可用时优雅回退 Tier 3。"""
    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test")

    def fake_ok(cfg, **kw):
        return {
            "items": [
                {
                    "idx": 0,
                    "candidates": [
                        {"knowledge_id": "math.geo.triangle", "reason": "涉及几何线段与角度关系"},
                        {"knowledge_id": "math.func.quadratic", "reason": "次优候选"},
                    ],
                }
            ]
        }

    monkeypatch.setattr(parser, "_post_deepseek_json", fake_ok)
    rows = parser.auto_associate_school_items(
        subject="math",
        knowledge_catalog=_MATH_CATALOG,
        items=[{"question_label": "第19题", "question_type": "解答题", "max_points": 5.0, "stem_text": "如图在平面图形中点P满足给定条件求证"}],
        use_ai=True,
    )
    assert rows[0]["method"] == "ai_matched"
    assert rows[0]["knowledge_id"] == "math.geo.triangle"
    assert len(rows[0]["draft_knowledge_candidates"]) == 3

    def fake_fail(cfg, **kw):
        raise parser.VisionParserUnavailableError("VISION_PARSER_TIMEOUT")

    monkeypatch.setattr(parser, "_post_deepseek_json", fake_fail)
    rows_fb = parser.auto_associate_school_items(
        subject="math",
        knowledge_catalog=_MATH_CATALOG,
        items=[{"question_label": "第19题", "question_type": "解答题", "max_points": 5.0, "stem_text": "如图在平面图形中点P满足给定条件求证"}],
        use_ai=True,
    )
    assert rows_fb[0]["method"] == "type_inferred"
    assert len(rows_fb[0]["draft_knowledge_candidates"]) == 3


def test_reflection_anti_perfunctory_local_and_ai_audit(monkeypatch):
    """防敷衍硬规则拦截套话/字数不足/重复刷屏，DeepSeek 语义审阅可追问打回并在无网时降级。"""
    # 1. 字数不足
    assert parser.validate_reflection_not_perfunctory("不会", "下次注意") is not None
    # 2. 连续重复字符与灌水
    assert parser.validate_reflection_not_perfunctory("111111111111111", "aaaaaaaaaaaaaaa") is not None
    # 3. 敷衍套话剥离后实质内容不足
    assert parser.validate_reflection_not_perfunctory("太粗心了没看清看错了", "下次一定注意认真审题多做练习") is not None
    # 4. 两栏复制粘贴雷同
    same = "一元二次方程求根公式分母漏乘二导致结果出错"
    assert parser.validate_reflection_not_perfunctory(same, same) is not None
    # 5. 具体实质分析通过本地校验
    good_stuck = "解分式方程时两边同乘最简公分母后忘记检验增根 x=2"
    good_fix = "以后每道分式方程解出未知数后，必须代回原分母验证不为零再作答"
    assert parser.validate_reflection_not_perfunctory(good_stuck, good_fix) is None

    # 6. 结构化编解码与退回重写保留原文
    encoded = parser.format_structured_reflection_note(good_stuck, good_fix)
    parsed = parser.parse_structured_reflection_note(encoded, "method", is_lost=True)
    assert parsed["reflection_status"] == "completed"
    assert parsed["stuck_point"] == good_stuck
    assert parsed["fix_strategy"] == good_fix

    returned = parser.format_returned_reflection_note("请补充说明为什么 x=2 是增根", encoded)
    parsed_ret = parser.parse_structured_reflection_note(returned, None, is_lost=True)
    assert parsed_ret["reflection_status"] == "needs_revision"
    assert parsed_ret["return_reason"] == "请补充说明为什么 x=2 是增根"
    assert parsed_ret["stuck_point"] == good_stuck

    # 7. AI 语义打回与超时降级
    monkeypatch.setenv("SHUTONG_AI_API_KEY", "sk-test")
    monkeypatch.setattr(
        parser,
        "_post_deepseek_json",
        lambda cfg, **kw: {"passed": False, "coach_feedback": "请写明具体哪一步公式代错？"},
    )
    passed, feedback, mode = parser.audit_reflection_with_deepseek(
        subject="math",
        topic="分式方程",
        question_label="第12题",
        stem_excerpt=None,
        error_category="method",
        stuck_point=good_stuck,
        fix_strategy=good_fix,
    )
    assert passed is False
    assert "公式" in (feedback or "")

    def fake_timeout(cfg, **kw):
        raise parser.VisionParserUnavailableError("VISION_PARSER_TIMEOUT")

    monkeypatch.setattr(parser, "_post_deepseek_json", fake_timeout)
    passed_fb, _, mode_fb = parser.audit_reflection_with_deepseek(
        subject="math",
        topic="分式方程",
        question_label="第12题",
        stem_excerpt=None,
        error_category="method",
        stuck_point=good_stuck,
        fix_strategy=good_fix,
    )
    assert passed_fb is True
    assert mode_fb == "local_rules_fallback"
