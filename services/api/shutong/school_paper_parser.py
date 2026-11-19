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
_VALID_CONFIDENCE = {
    "high",
    "medium",
    "low",
    "skeleton_only",
    "external_sync",
    "auto_matched",
    "ai_matched",
    "type_inferred",
}
_CONFIDENCE_TO_SOURCE_LABEL = {
    "high": "高置信识别草稿",
    "medium": "中等置信草稿",
    "low": "低置信待人工核对",
    "skeleton_only": "仅原卷题号与分值骨架",
    "external_sync": "外部平台抓取待核对",
    "auto_matched": "关键词自动关联",
    "ai_matched": "AI 语义智能关联",
    "type_inferred": "题型考纲先验关联",
}

_SUBJECT_CN = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "physics": "物理",
    "ethics": "道法",
}

_ETHICS_CANDIDATES: tuple[dict[str, str], ...] = (
    {"knowledge_id": "ethics.general", "title": "道法综合主题", "reason": "道德与法治主观分析通用复盘主题"},
    {"knowledge_id": "ethics.law_citizenship", "title": "法治与公民权利义务", "reason": "涉及宪法、未成年人保护、依法治国与社会规则"},
    {"knowledge_id": "ethics.national_values", "title": "家国情怀与核心价值观", "reason": "涉及国情国策、文化自信与个人社会责任"},
)

# 5 学科叶子考点高频同义关键词映射（Tier 1 本地极速匹配）
_SUBJECT_KEYWORD_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    "math": {
        "math_cand.num.rational": ("有理数", "相反数", "绝对值", "数轴", "科学记数法", "倒数", "近似数", "乘方"),
        "math_cand.num.real": ("实数", "无理数", "平方根", "算术平方根", "立方根", "估算"),
        "math_cand.alg.poly": ("整式", "单项式", "多项式", "同类项", "幂的运算", "乘法公式", "完全平方", "平方差"),
        "math_cand.alg.factor": ("因式分解", "提公因式", "十字相乘"),
        "math_cand.alg.frac": ("分式", "约分", "通分", "分式化简", "无意义", "值为零", "值为0"),
        "math_cand.alg.quadratic_radical": ("二次根式", "√", "最简二次根式", "分母有理化", "化简求值"),
        "math_cand.eq.linear": ("一元一次方程", "去分母", "移项"),
        "math_cand.eq.linear_system": ("二元一次方程", "方程组", "消元", "代入消元", "加减消元"),
        "math_cand.eq.quadratic": ("一元二次方程", "求根", "配方法", "判别式", "韦达", "根的判别", "增长率", "x²"),
        "math_cand.eq.fractional": ("分式方程", "增根", "工程问题", "行程问题"),
        "math_cand.ineq.linear": ("不等式", "不等式组", "解集", "最大整数", "至少", "不超过"),
        "math_cand.func.basic": ("自变量", "取值范围", "函数图象", "函数图像"),
        "math_cand.func.linear": ("一次函数", "正比例函数", "y=kx", "斜率", "截距", "交点坐标"),
        "math_cand.func.inverse": ("反比例", "k/x", "双曲线"),
        "math_cand.func.quadratic": ("二次函数", "抛物线", "顶点", "对称轴", "y=ax", "开口", "最大值", "最小值"),
        "math_cand.geo.lines_angles": ("补角", "余角", "对顶角", "平行线", "同位角", "内错角", "尺规作图"),
        "math_cand.geo.triangle_basic": ("三角形", "内角和", "外角", "三边关系", "中线", "角平分线"),
        "math_cand.geo.isosceles_triangle": ("等腰三角形", "等边三角形", "三线合一", "顶角", "底角"),
        "math_cand.geo.pythagoras": ("勾股", "直角三角形", "斜边", "c²=a²+b²"),
        "math_cand.geo.congruent_triangles": ("全等", "SAS", "ASA", "AAS", "SSS", "HL", "全等三角形"),
        "math_cand.geo.quadrilateral_basic": ("多边形", "平行四边形", "内角和公式", "对角线"),
        "math_cand.geo.special_parallelogram": ("矩形", "菱形", "正方形", "中点四边形"),
        "math_cand.geo.circle_basic": ("垂径定理", "圆心角", "圆周角", "外接圆", "内切圆"),
        "math_cand.geo.circle_tangent": ("切线", "相切", "切线长", "切点"),
        "math_cand.geo.arc_sector": ("弧长", "扇形", "圆锥", "阴影面积", "侧面积"),
        "math_cand.geo.proof_logic": ("逆命题", "反证法", "真命题", "假命题", "几何证明"),
        "math_cand.geo.transform_symmetry": ("轴对称", "中心对称", "平移", "旋转", "折叠", "对称图形"),
        "math_cand.geo.similarity": ("相似", "位似", "比例线段", "黄金分割"),
        "math_cand.geo.trigonometry": ("sin", "cos", "tan", "锐角三角函数", "仰角", "俯角", "坡度", "解直角三角形"),
        "math_cand.geo.projection_views": ("三视图", "主视图", "左视图", "俯视图", "展开图", "正方体"),
        "math_cand.geo.coordinates": ("平面直角坐标系", "坐标系", "象限", "点坐标", "坐标变换"),
        "math_cand.stat.sampling_collection": ("抽样", "普查", "总体", "样本", "扇形图", "条形图", "频数分布"),
        "math_cand.stat.central_dispersion": ("平均数", "中位数", "众数", "方差", "极差", "稳定性"),
        "math_cand.prob.probability": ("概率", "随机事件", "必然事件", "树状图", "列表法", "摸球", "卡片"),
        "math_cand.prac.project_modeling": ("综合与实践", "实际应用", "建模", "方案设计", "最省", "利润"),
        "math_cand.prac.exploration_new_definition": ("新定义", "关联点", "规律探究", "代数综合", "几何综合", "压轴"),
    },
    "chinese": {
        "chinese_cand.base.phonetics": ("注音", "读音", "字音", "多音字", "声调"),
        "chinese_cand.base.character_orthography": ("错别字", "字形", "笔顺", "书写", "正字"),
        "chinese_cand.base.idiom_vocabulary": ("成语", "词语", "近义词", "词义", "熟语"),
        "chinese_cand.base.syntax_revision": ("病句", "语病", "修改", "语序", "衔接", "排序"),
        "chinese_cand.base.punctuation": ("标点", "顿号", "分号", "引号", "破折号"),
        "chinese_cand.base.culture_calligraphy": ("文化常识", "书法", "对联", "节气", "礼仪"),
        "chinese_cand.base.contextual_expression": ("语境", "补写", "拟写", "标语", "情境表达"),
        "chinese_cand.poetry.dictation": ("默写", "古诗文默写", "理解性默写", "填空"),
        "chinese_cand.poetry.appreciation": ("古诗", "诗词", "赏析", "意象", "炼字", "绝句"),
        "chinese_cand.prose.classical_vocab": ("实词", "虚词", "一词多义", "通假字", "古今异义", "加点"),
        "chinese_cand.prose.classical_syntax_trans": ("文言文", "翻译", "断句", "句式", "倒装"),
        "chinese_cand.prose.classical_comprehension": ("文言", "人物形象", "道理", "对比阅读"),
        "chinese_cand.reading.informative_skills": ("说明文", "信息提取", "说明方法", "说明顺序", "举例子", "列数字"),
        "chinese_cand.reading.multimodal_non_continuous": ("非连续性", "材料一", "材料二", "图表", "多则材料"),
        "chinese_cand.reading.narrative_plot_character": ("记叙文", "小说", "散文", "情节", "环境描写", "心理描写"),
        "chinese_cand.reading.narrative_language_theme": ("修辞", "赏析句子", "比喻", "拟人", "主旨", "标题含义"),
        "chinese_cand.reading.argument_claims_evidence": ("议论文", "论点", "中心论点", "论据", "事实论据"),
        "chinese_cand.reading.argument_methods_structure": ("论证方法", "论证思路", "举例论证", "道理论证", "对比论证"),
        "chinese_cand.reading.classic_whole_book": ("名著", "朝花夕拾", "西游记", "红星照耀中国", "水浒传", "骆驼祥子"),
        "chinese_cand.writing.composition_narrative": ("大作文", "记叙文写作", "半命题", "命题作文", "600字"),
        "chinese_cand.writing.critical_micro_writing": ("微写作", "小作文", "推荐语", "评论", "通知"),
    },
    "english": {
        "english_cand.vocab.formation": ("构词", "前缀", "后缀", "派生", "词性转换"),
        "english_cand.vocab.collocation_context": ("完形", "固定搭配", "短语", "语境选词", "词义辨析"),
        "english_cand.noun.number_case": ("名词", "复数", "不可数", "所有格"),
        "english_cand.pronoun.types": ("代词", "人称代词", "物主代词", "反身代词", "不定代词"),
        "english_cand.preposition.usage": ("介词", "in", "on", "at", "with", "for", "by"),
        "english_cand.article.rules": ("冠词", "a/an", "零冠词"),
        "english_cand.adj_adv.comparison": ("形容词", "副词", "比较级", "最高级"),
        "english_cand.numeral.rules": ("数词", "基数词", "序数词", "hundred", "million"),
        "english_cand.tense.present_past": ("一般现在时", "一般过去时", "三单", "did", "was", "were"),
        "english_cand.tense.future_continuous": ("将来时", "进行时", "will", "be going to", "was doing"),
        "english_cand.tense.present_perfect": ("现在完成时", "have done", "has been", "since"),
        "english_cand.voice.passive": ("被动语态", "be done", "was built", "is made"),
        "english_cand.modal.verbs": ("情态动词", "can", "must", "may", "should", "might"),
        "english_cand.non_finite.verbs": ("非谓语", "不定式", "动名词", "doing", "to do"),
        "english_cand.clause.simple_sentences": ("感叹句", "祈使句", "反意疑问句", "there be", "疑问词"),
        "english_cand.syntax.compound_conjunction": ("连词", "and", "but", "or", "并列句"),
        "english_cand.syntax.object_clause": ("宾语从句", "陈述语序", "whether"),
        "english_cand.syntax.adverbial_clause": ("状语从句", "when", "because", "although", "until"),
        "english_cand.syntax.attributive_clause": ("定语从句", "which", "who", "whose", "关系代词"),
        "english_cand.listening_speaking": ("听力", "情景交际", "口语", "听后记录", "转述"),
        "english_cand.reading.facts_inference": ("阅读理解", "细节理解", "推理判断", "词义猜测", "主旨大意"),
        "english_cand.reading.task_based": ("阅读表达", "任务型阅读", "回答问题", "还原句子", "七选五", "五选五"),
        "english_cand.writing.composition": ("书面表达", "文段表达", "作文", "书信", "演讲稿"),
    },
    "physics": {
        "physics_cand.matter.thermal_state": ("物态变化", "熔化", "凝固", "汽化", "液化", "升华", "凝华", "温度计", "沸腾"),
        "physics_cand.matter.density_prop": ("密度", "质量", "天平", "量筒", "ρ=m/V"),
        "physics_cand.matter.micro_structure": ("分子", "扩散", "原子", "热运动", "分子间作用力"),
        "physics_cand.motion.speed": ("机械运动", "参照物", "速度", "v=s/t", "平均速度", "刻度尺"),
        "physics_cand.force.basics": ("力的作用效果", "弹力", "弹簧测力计", "力的示意图"),
        "physics_cand.force.gravity_friction": ("重力", "G=mg", "摩擦力", "静摩擦", "滑动摩擦"),
        "physics_cand.force.newton_balance": ("牛顿第一定律", "惯性", "二力平衡", "受力分析", "合力"),
        "physics_cand.force.pressure_fluid": ("压强", "p=F/S", "液体压强", "p=ρgh", "连通器", "大气压", "流体压强"),
        "physics_cand.force.buoyancy": ("浮力", "阿基米德", "漂浮", "悬浮", "下沉", "F浮"),
        "physics_cand.force.simple_machine": ("杠杆", "滑轮", "滑轮组", "动滑轮", "定滑轮", "机械效率", "杠杆平衡"),
        "physics_cand.sound": ("声现象", "音调", "响度", "音色", "声速", "噪声", "超声波"),
        "physics_cand.light.propagate_reflect": ("光的直线传播", "光的反射", "平面镜成像", "小孔成像", "虚像"),
        "physics_cand.light.refract_dispersion": ("光的折射", "色散", "三棱镜", "红绿蓝"),
        "physics_cand.light.lens_application": ("凸透镜", "凹透镜", "成像规律", "照相机", "投影仪", "放大镜", "近视"),
        "physics_cand.elec.charge_field": ("电荷", "摩擦起电", "导体", "绝缘体", "验电器"),
        "physics_cand.elec.electromagnetism": ("磁场", "磁感线", "安培定则", "电磁铁", "电动机", "发电机", "电磁感应"),
        "physics_cand.energy.transfer_concept": ("能量转化", "能源", "可再生", "不可再生", "核能", "太阳能"),
        "physics_cand.energy.work_power_eff": ("功率", "W=Fs", "P=W/t", "有用功", "总功"),
        "physics_cand.energy.mech_energy_conserv": ("动能", "重力势能", "弹性势能", "机械能", "机械能守恒"),
        "physics_cand.energy.internal_heat": ("内能", "热传递", "做功改变内能", "比热容", "Q=cmΔt", "热值"),
        "physics_cand.energy.heat_engine": ("热机", "四冲程", "内燃机", "热机效率", "做功冲程"),
        "physics_cand.energy.circuit_rules": ("串联", "并联", "电路图", "电流表", "电压表", "电流规律", "电压规律"),
        "physics_cand.energy.ohm_law": ("欧姆定律", "电阻", "滑动变阻器", "I=U/R", "伏安法"),
        "physics_cand.energy.electric_power_joule": ("电功", "电功率", "P=UI", "焦耳定律", "Q=I²Rt", "电能表", "额定功率"),
        "physics_cand.energy.safety_and_conservation": ("家庭电路", "安全用电", "测电笔", "保险丝", "空气开关", "触电"),
        "physics_cand.exp.measuring_skills": ("读数", "示数", "测密度", "伏安法测电阻", "量程", "分度值"),
        "physics_cand.exp.inquiry_methods": ("探究", "控制变量", "转换法", "实验结论", "误差分析", "实验设计"),
        "physics_cand.interdisciplinary.life_engineer": ("科普阅读", "生活物理", "跨学科实践", "航天", "高铁"),
        "physics_cand.interdisciplinary.society_development": ("环境保护", "低碳", "新能源", "社会发展"),
    },
}

# 旧锚点词补充映射（兼容未带 *_cand 前缀的发布态节点）
_LEGACY_KEYWORD_ANCHORS: dict[str, tuple[str, ...]] = {
    "二次方程": ("一元二次", "求根", "配方法", "判别式", "韦达", "x²"),
    "二次函数": ("抛物线", "顶点", "对称轴", "y=ax", "开口"),
    "反比例函数": ("反比例", "k/x", "双曲线"),
    "全等": ("△", "平分线", "垂直", "证明", "全等", "相似"),
    "三角": ("△", "三角形", "勾股", "斜边", "∠"),
    "几何": ("坐标系", "直线", "线段", "面积", "对称", "旋转", "圆"),
    "概率": ("卡片", "随机", "概率", "统计", "平均"),
    "算术": ("计算", "实数", "绝对值", "根式", "增长率", "不等式"),
    "方程": ("求解", "列方程", "应用题"),
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


def _leaf_catalog_nodes(knowledge_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤非选修的叶子知识点节点（排除仅作分类容器的父节点）。"""
    valid = [n for n in knowledge_catalog if n.get("code") and not n.get("is_elective")]
    if not valid:
        valid = [n for n in knowledge_catalog if n.get("code")]
    parent_codes = {str(n.get("parent_code") or "").strip() for n in valid if n.get("parent_code")}
    leaves = [n for n in valid if str(n["code"]) not in parent_codes]
    return leaves or valid


def _prior_candidates_for_item(
    subject: str,
    question_label: str,
    question_type: str | None,
    max_points: float | None,
    leaf_nodes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Tier 3 确定性先验矩阵：按学科 × 题型 × 题号/分值段挑选 Top-3 课标叶子考点。"""
    if subject not in _CORE_SUBJECTS:
        return list(_ETHICS_CANDIDATES)
    if not leaf_nodes:
        return []

    by_code = {str(n["code"]): str(n.get("name") or n["code"]) for n in leaf_nodes if n.get("code")}
    m_num = re.search(r"(\d+)", str(question_label or ""))
    qnum = int(m_num.group(1)) if m_num else 1
    qtype = str(question_type or "").strip()
    pts = float(max_points or 0.0)

    preferred: list[str] = []
    if subject == "math":
        if "选择" in qtype or ("填空" not in qtype and "解答" not in qtype and "计算" not in qtype and qnum <= 8):
            if qnum <= 3:
                preferred = ["math_cand.num.rational", "math_cand.geo.transform_symmetry", "math_cand.alg.poly"]
            elif qnum <= 6:
                preferred = ["math_cand.geo.lines_angles", "math_cand.prob.probability", "math_cand.eq.quadratic"]
            else:
                preferred = ["math_cand.func.linear", "math_cand.geo.circle_basic", "math_cand.func.quadratic"]
        elif "填空" in qtype or (9 <= qnum <= 16 and "解答" not in qtype):
            if qnum <= 12:
                preferred = ["math_cand.alg.frac", "math_cand.alg.factor", "math_cand.ineq.linear"]
            else:
                preferred = ["math_cand.func.inverse", "math_cand.stat.central_dispersion", "math_cand.geo.arc_sector"]
        elif qnum <= 22 or "计算" in qtype or (0 < pts < 6):
            if qnum <= 18:
                preferred = ["math_cand.alg.quadratic_radical", "math_cand.ineq.linear", "math_cand.alg.frac"]
            elif qnum <= 21:
                preferred = ["math_cand.geo.congruent_triangles", "math_cand.eq.linear_system", "math_cand.geo.special_parallelogram"]
            else:
                preferred = ["math_cand.func.linear", "math_cand.func.inverse", "math_cand.stat.sampling_collection"]
        else:
            if qnum <= 24:
                preferred = ["math_cand.geo.circle_tangent", "math_cand.geo.similarity", "math_cand.stat.central_dispersion"]
            else:
                preferred = ["math_cand.func.quadratic", "math_cand.geo.transform_symmetry", "math_cand.prac.exploration_new_definition"]
    elif subject == "chinese":
        if "默写" in qtype or (7 <= qnum <= 8 and "选择" not in qtype):
            preferred = ["chinese_cand.poetry.dictation", "chinese_cand.poetry.appreciation", "chinese_cand.base.culture_calligraphy"]
        elif "名著" in qtype or qnum == 9:
            preferred = ["chinese_cand.reading.classic_whole_book", "chinese_cand.base.contextual_expression", "chinese_cand.poetry.appreciation"]
        elif "古诗" in qtype or (10 <= qnum <= 11):
            preferred = ["chinese_cand.poetry.appreciation", "chinese_cand.prose.classical_vocab", "chinese_cand.poetry.dictation"]
        elif "文言" in qtype or (12 <= qnum <= 15):
            preferred = ["chinese_cand.prose.classical_vocab", "chinese_cand.prose.classical_syntax_trans", "chinese_cand.prose.classical_comprehension"]
        elif "非连" in qtype or "说明" in qtype or (16 <= qnum <= 18):
            preferred = ["chinese_cand.reading.multimodal_non_continuous", "chinese_cand.reading.informative_skills", "chinese_cand.reading.argument_claims_evidence"]
        elif "作文" in qtype or "写作" in qtype or pts >= 20 or qnum >= 23:
            preferred = ["chinese_cand.writing.composition_narrative", "chinese_cand.writing.critical_micro_writing", "chinese_cand.reading.narrative_language_theme"]
        elif "基础" in qtype or qnum <= 6:
            preferred = ["chinese_cand.base.contextual_expression", "chinese_cand.base.character_orthography", "chinese_cand.base.idiom_vocabulary"]
        else:
            preferred = ["chinese_cand.reading.narrative_plot_character", "chinese_cand.reading.narrative_language_theme", "chinese_cand.reading.argument_methods_structure"]
    elif subject == "english":
        if "听力" in qtype:
            preferred = ["english_cand.listening_speaking", "english_cand.reading.facts_inference", "english_cand.vocab.collocation_context"]
        elif "写作" in qtype or "作文" in qtype or pts >= 8 or qnum >= 38:
            preferred = ["english_cand.writing.composition", "english_cand.tense.present_past", "english_cand.vocab.collocation_context"]
        elif "表达" in qtype or "简答" in qtype or (34 <= qnum <= 37):
            preferred = ["english_cand.reading.task_based", "english_cand.reading.facts_inference", "english_cand.tense.present_past"]
        elif "完形" in qtype or (13 <= qnum <= 20):
            preferred = ["english_cand.vocab.collocation_context", "english_cand.vocab.formation", "english_cand.syntax.compound_conjunction"]
        elif "阅读" in qtype or (21 <= qnum <= 33):
            preferred = ["english_cand.reading.facts_inference", "english_cand.vocab.collocation_context", "english_cand.reading.task_based"]
        elif qnum <= 4:
            preferred = ["english_cand.pronoun.types", "english_cand.preposition.usage", "english_cand.adj_adv.comparison"]
        elif qnum <= 8:
            preferred = ["english_cand.tense.present_past", "english_cand.modal.verbs", "english_cand.tense.present_perfect"]
        else:
            preferred = ["english_cand.voice.passive", "english_cand.syntax.object_clause", "english_cand.syntax.adverbial_clause"]
    elif subject == "physics":
        if "多选" in qtype or (13 <= qnum <= 15):
            preferred = ["physics_cand.force.buoyancy", "physics_cand.energy.electric_power_joule", "physics_cand.energy.internal_heat"]
        elif "实验" in qtype or (21 <= qnum <= 26):
            preferred = ["physics_cand.exp.inquiry_methods", "physics_cand.exp.measuring_skills", "physics_cand.energy.ohm_law"]
        elif "科普" in qtype or (27 <= qnum <= 28):
            preferred = ["physics_cand.interdisciplinary.life_engineer", "physics_cand.energy.transfer_concept", "physics_cand.force.pressure_fluid"]
        elif "计算" in qtype or qnum >= 29 or pts >= 4:
            preferred = ["physics_cand.energy.electric_power_joule", "physics_cand.force.pressure_fluid", "physics_cand.energy.work_power_eff"]
        elif "填空" in qtype or (16 <= qnum <= 20):
            preferred = ["physics_cand.exp.measuring_skills", "physics_cand.light.lens_application", "physics_cand.energy.safety_and_conservation"]
        elif qnum <= 4:
            preferred = ["physics_cand.light.propagate_reflect", "physics_cand.matter.thermal_state", "physics_cand.sound"]
        elif qnum <= 8:
            preferred = ["physics_cand.force.newton_balance", "physics_cand.force.pressure_fluid", "physics_cand.energy.mech_energy_conserv"]
        else:
            preferred = ["physics_cand.energy.circuit_rules", "physics_cand.energy.ohm_law", "physics_cand.elec.electromagnetism"]

    basis = f"{qtype or '题号'}第{qnum}题考纲先验"
    out: list[dict[str, str]] = []
    for code in preferred:
        if code in by_code:
            out.append({"knowledge_id": code, "title": by_code[code], "reason": basis})
    return out


def ensure_three_candidates(
    candidates: list[dict[str, str]] | None,
    *,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    question_label: str = "第1题",
    question_type: str | None = None,
    max_points: float | None = None,
    fallback_candidates: list[dict[str, str]] | None = None,
    limit: int = 3,
) -> list[dict[str, str]]:
    """确保每题均返回合法且去重的 3 个候选考点（非核心学科返回 3 个道法主题）。"""
    if subject not in _CORE_SUBJECTS:
        seen_eth: set[str] = set()
        eth_out: list[dict[str, str]] = []
        for entry in [*(candidates or []), *(fallback_candidates or []), *_ETHICS_CANDIDATES]:
            kid = str(entry.get("knowledge_id") or "").strip()
            if not kid or kid == "unmapped" or kid in seen_eth:
                continue
            seen_eth.add(kid)
            eth_out.append(
                {
                    "knowledge_id": kid,
                    "title": str(entry.get("title") or kid),
                    "reason": str(entry.get("reason") or "道法复盘主题"),
                }
            )
            if len(eth_out) >= limit:
                break
        return eth_out

    leaf_nodes = _leaf_catalog_nodes(knowledge_catalog)
    all_names = {str(n["code"]): str(n.get("name") or n["code"]) for n in knowledge_catalog if n.get("code")}
    prior = _prior_candidates_for_item(subject, question_label, question_type, max_points, leaf_nodes)

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in [*(candidates or []), *(fallback_candidates or []), *prior]:
        kid = str(entry.get("knowledge_id") or "").strip()
        if not kid or kid == "unmapped" or kid not in all_names or kid in seen:
            continue
        seen.add(kid)
        out.append(
            {
                "knowledge_id": kid,
                "title": all_names[kid],
                "reason": str(entry.get("reason") or "同科核心考点候选"),
            }
        )
        if len(out) >= limit:
            return out

    for node in [*leaf_nodes, *knowledge_catalog]:
        code = str(node.get("code") or "").strip()
        if not code or code == "unmapped" or code in seen:
            continue
        seen.add(code)
        out.append(
            {
                "knowledge_id": code,
                "title": str(node.get("name") or code),
                "reason": "同科叶子考点补齐候选",
            }
        )
        if len(out) >= limit:
            break
    return out


def _score_knowledge_candidates(
    snippet: str,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    *,
    limit: int = 3,
    question_label: str = "第1题",
    question_type: str | None = None,
    max_points: float | None = None,
) -> tuple[list[dict[str, str]], float]:
    """内部打分函数：返回 (候选列表, 最高命中分)，优先叶子节点。"""
    if subject not in _CORE_SUBJECTS:
        return list(_ETHICS_CANDIDATES)[:limit], 2.0
    if not knowledge_catalog:
        return [], 0.0

    leaf_nodes = _leaf_catalog_nodes(knowledge_catalog)
    lowered_snippet = (snippet or "").lower()
    snippet_tokens = _tokenize_chinese_text(snippet)
    subject_hints = _SUBJECT_KEYWORD_HINTS.get(subject, {})
    scored: list[tuple[float, dict[str, Any], list[str]]] = []

    for node in leaf_nodes:
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

        # 精准叶子编码同义词映射（5 学科通用）
        for hint_code, keywords in subject_hints.items():
            if code == hint_code or code.startswith(f"{hint_code}."):
                hits = [kw for kw in keywords if kw.lower() in lowered_snippet]
                if hits:
                    score += min(6.0, len(hits) * 2.0)
                    reasons.append(f"关键词命中({hits[0]})")

        # 兼容未迁移旧锚点
        for anchor, hints in _LEGACY_KEYWORD_ANCHORS.items():
            if anchor in f"{name} {desc}":
                hit_count = sum(1 for h in hints if h.lower() in lowered_snippet)
                if hit_count:
                    score += hit_count * 1.4
                    reasons.append(f"特征词命中({anchor})")

        node_tokens = _tokenize_chinese_text(f"{name} {desc}")
        overlap = snippet_tokens & node_tokens
        if overlap:
            score += min(3.6, len(overlap) * 0.6)
            if not reasons:
                reasons.append("题干文本相似度匹配")

        scored.append((score, node, reasons))

    scored.sort(key=lambda item: (-item[0], str(item[1].get("code") or "")))
    top_score = scored[0][0] if scored else 0.0
    matched = [
        {
            "knowledge_id": str(node["code"]),
            "title": str(node.get("name") or node["code"]),
            "reason": "、".join(dict.fromkeys(reasons)) if reasons else "同科核心考点候选",
        }
        for sc, node, reasons in scored[:limit]
        if sc > 0
    ]
    padded = ensure_three_candidates(
        matched,
        subject=subject,
        knowledge_catalog=knowledge_catalog,
        question_label=question_label,
        question_type=question_type,
        max_points=max_points,
        limit=limit,
    )
    return padded, top_score


def match_knowledge_candidates(
    snippet: str,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    *,
    limit: int = 3,
    question_label: str = "第1题",
    question_type: str | None = None,
    max_points: float | None = None,
) -> list[dict[str, str]]:
    """基于关键词与发布态知识点目录匹配 Top-N 候选编码（保证补足 3 项，纯本地规则）。"""
    candidates, _ = _score_knowledge_candidates(
        snippet,
        subject,
        knowledge_catalog,
        limit=limit,
        question_label=question_label,
        question_type=question_type,
        max_points=max_points,
    )
    return candidates


def _extract_question_type_from_reason(reason: str | None) -> str | None:
    m = re.search(r"题型\s*[=＝:]\s*([^\s；;，,]+)", str(reason or ""))
    if not m:
        return None
    val = m.group(1).strip()
    return None if val in {"", "未知", "None"} else val


def auto_associate_school_items(
    *,
    subject: str,
    knowledge_catalog: list[dict[str, Any]],
    items: list[dict[str, Any]],
    use_ai: bool = True,
) -> list[dict[str, Any]]:
    """三层渐进式校考知识点自动关联管线：Tier 1 本地关键词 -> Tier 2 DeepSeek 语义 -> Tier 3 考纲先验。

    返回与输入 `items` 等长的关联结果列表，每项固定包含：
    `knowledge_id`, `draft_knowledge_candidates` (len=3, 仅道法固定 3 主题), `draft_confidence`, `method`, `basis_note`。
    """
    if not items:
        return []

    leaf_nodes = _leaf_catalog_nodes(knowledge_catalog)
    valid_codes = {str(n["code"]): str(n.get("name") or n["code"]) for n in knowledge_catalog if n.get("code")}
    results: list[dict[str, Any] | None] = [None] * len(items)
    tier2_indices: list[int] = []

    for idx, row in enumerate(items):
        label = normalize_question_label(str(row.get("question_label") or f"第{idx + 1}题"))
        qtype = str(row.get("question_type") or "").strip() or _extract_question_type_from_reason(row.get("draft_reason"))
        max_pts = row.get("max_points")
        stem = str(row.get("stem_text") or "").strip()

        if subject not in _CORE_SUBJECTS:
            cands = ensure_three_candidates(
                None,
                subject=subject,
                knowledge_catalog=knowledge_catalog,
                question_label=label,
                question_type=qtype,
                max_points=max_pts,
            )
            results[idx] = {
                "knowledge_id": cands[0]["knowledge_id"] if cands else "ethics.general",
                "draft_knowledge_candidates": cands,
                "draft_confidence": "type_inferred",
                "method": "type_inferred",
                "basis_note": "道法主题智能先验",
            }
            continue

        cands, top_score = _score_knowledge_candidates(
            stem,
            subject,
            knowledge_catalog,
            limit=3,
            question_label=label,
            question_type=qtype,
            max_points=max_pts,
        )
        if stem and top_score >= 2.0 and cands:
            results[idx] = {
                "knowledge_id": cands[0]["knowledge_id"],
                "draft_knowledge_candidates": cands,
                "draft_confidence": "auto_matched",
                "method": "auto_matched",
                "basis_note": cands[0]["reason"],
            }
        elif stem and len(stem) >= 6 and use_ai:
            tier2_indices.append(idx)
        else:
            prior_cands = ensure_three_candidates(
                None,
                subject=subject,
                knowledge_catalog=knowledge_catalog,
                question_label=label,
                question_type=qtype,
                max_points=max_pts,
                fallback_candidates=cands,
            )
            results[idx] = {
                "knowledge_id": prior_cands[0]["knowledge_id"] if prior_cands else "unmapped",
                "draft_knowledge_candidates": prior_cands,
                "draft_confidence": "type_inferred",
                "method": "type_inferred",
                "basis_note": prior_cands[0]["reason"] if prior_cands else "题型考纲先验",
            }

    # Tier 2: 对有题干文本但未强命中本地关键词的题目调用 DeepSeek 文本模型批量语义推荐 Top-3
    if tier2_indices and subject in _CORE_SUBJECTS and leaf_nodes:
        cfg = load_vision_config(require_key=False)
        if cfg is not None:
            subject_cn = _SUBJECT_CN.get(subject, subject)
            catalog_lines = "\n".join(f"- {n['code']} : {n.get('name', n['code'])}" for n in leaf_nodes[:120])
            ai_by_key: dict[str, dict[str, Any]] = {}
            batch_size = 18
            try:
                for start in range(0, len(tier2_indices), batch_size):
                    chunk_idxs = tier2_indices[start : start + batch_size]
                    payload_rows = [
                        {
                            "idx": i,
                            "question_label": normalize_question_label(str(items[i].get("question_label") or f"第{i + 1}题")),
                            "question_type": str(items[i].get("question_type") or "") or _extract_question_type_from_reason(items[i].get("draft_reason")) or "",
                            "stem_text": str(items[i].get("stem_text") or "")[:400],
                        }
                        for i in chunk_idxs
                    ]
                    prompt = (
                        f"请为以下【{subject_cn}】校考试题匹配 Top-3 最贴合的课标考点。\n"
                        "只输出严格 JSON 对象 {\"items\": [{\"idx\": 数字, \"candidates\": [{\"knowledge_id\": \"编码\", \"reason\": \"20字内依据\"}]}]}。\n"
                        "要求：knowledge_id 必须严格选自下方列表，按相关性从高到低给出 3 个。\n"
                        f"合法叶子考点列表：\n{catalog_lines}\n\n待匹配题目：\n{json.dumps(payload_rows, ensure_ascii=False)}"
                    )
                    data = _post_deepseek_json(
                        cfg,
                        model=cfg.text_model,
                        messages=[
                            {"role": "system", "content": "你是初中课标考点智能标注助手，只输出严格 JSON 对象。"},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=4096,
                    )
                    for ai_row in data.get("items") or []:
                        if isinstance(ai_row, dict) and ai_row.get("idx") is not None:
                            ai_by_key[str(ai_row["idx"])] = ai_row
            except VisionParserUnavailableError:
                ai_by_key = {}

            for i in tier2_indices:
                row = items[i]
                label = normalize_question_label(str(row.get("question_label") or f"第{i + 1}题"))
                qtype = str(row.get("question_type") or "").strip() or _extract_question_type_from_reason(row.get("draft_reason"))
                ai_row = ai_by_key.get(str(i))
                parsed_ai: list[dict[str, str]] = []
                if ai_row and isinstance(ai_row.get("candidates"), list):
                    for cand in ai_row["candidates"]:
                        if not isinstance(cand, dict):
                            continue
                        kid = str(cand.get("knowledge_id") or "").strip()
                        if kid in valid_codes:
                            parsed_ai.append(
                                {
                                    "knowledge_id": kid,
                                    "title": valid_codes[kid],
                                    "reason": str(cand.get("reason") or "AI 语义精准匹配")[:80],
                                }
                            )
                local_cands, _ = _score_knowledge_candidates(
                    str(row.get("stem_text") or ""),
                    subject,
                    knowledge_catalog,
                    limit=3,
                    question_label=label,
                    question_type=qtype,
                    max_points=row.get("max_points"),
                )
                if parsed_ai:
                    final_cands = ensure_three_candidates(
                        parsed_ai,
                        subject=subject,
                        knowledge_catalog=knowledge_catalog,
                        question_label=label,
                        question_type=qtype,
                        max_points=row.get("max_points"),
                        fallback_candidates=local_cands,
                    )
                    results[i] = {
                        "knowledge_id": final_cands[0]["knowledge_id"],
                        "draft_knowledge_candidates": final_cands,
                        "draft_confidence": "ai_matched",
                        "method": "ai_matched",
                        "basis_note": f"AI语义:{final_cands[0]['reason']}",
                    }

    for i, res in enumerate(results):
        if res is not None:
            continue
        row = items[i]
        label = normalize_question_label(str(row.get("question_label") or f"第{i + 1}题"))
        qtype = str(row.get("question_type") or "").strip() or _extract_question_type_from_reason(row.get("draft_reason"))
        prior_cands = ensure_three_candidates(
            None,
            subject=subject,
            knowledge_catalog=knowledge_catalog,
            question_label=label,
            question_type=qtype,
            max_points=row.get("max_points"),
        )
        results[i] = {
            "knowledge_id": prior_cands[0]["knowledge_id"] if prior_cands else ("ethics.general" if subject not in _CORE_SUBJECTS else "unmapped"),
            "draft_knowledge_candidates": prior_cands,
            "draft_confidence": "type_inferred",
            "method": "type_inferred",
            "basis_note": prior_cands[0]["reason"] if prior_cands else "题型考纲先验",
        }

    return [r for r in results if r is not None]


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

        qlabel = f"第{qnum}题"
        candidates = match_knowledge_candidates(
            snippet,
            subject,
            knowledge_catalog,
            limit=3,
            question_label=qlabel,
            max_points=max_pts,
        )
        primary_kid = candidates[0]["knowledge_id"] if candidates else ("ethics.general" if subject not in _CORE_SUBJECTS else "unmapped")
        items.append(
            {
                "question_label": qlabel,
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
        fallback_candidates = match_knowledge_candidates(
            stem_hint,
            subject,
            knowledge_catalog,
            limit=3,
            question_label=label,
            max_points=max_pts,
        )

        if subject not in _CORE_SUBJECTS:
            final_kid = raw_kid if raw_kid and raw_kid != "unmapped" and len(raw_kid) <= 100 else "ethics.general"
            primary_cands = [{"knowledge_id": final_kid, "title": "道法综合主题" if final_kid == "ethics.general" else final_kid, "reason": "非核心刷题学科复盘主题"}]
            candidates = ensure_three_candidates(
                primary_cands,
                subject=subject,
                knowledge_catalog=knowledge_catalog,
                question_label=label,
                max_points=max_pts,
            )
            final_kid = candidates[0]["knowledge_id"] if candidates else final_kid
        elif raw_kid in valid_codes:
            final_kid = raw_kid
            candidates = ensure_three_candidates(
                [{"knowledge_id": raw_kid, "title": valid_codes[raw_kid], "reason": "模型直接匹配课标编码"}],
                subject=subject,
                knowledge_catalog=knowledge_catalog,
                question_label=label,
                max_points=max_pts,
                fallback_candidates=fallback_candidates,
            )
        else:
            candidates = ensure_three_candidates(
                fallback_candidates,
                subject=subject,
                knowledge_catalog=knowledge_catalog,
                question_label=label,
                max_points=max_pts,
            )
            final_kid = candidates[0]["knowledge_id"] if candidates else (next(iter(valid_codes), "unmapped"))

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


_PERFUNCTORY_CLICHES: tuple[str, ...] = (
    "下次一定注意",
    "下次注意",
    "下次认真",
    "下次小心",
    "认真审题",
    "仔细审题",
    "多做练习",
    "多刷题",
    "多做题",
    "好好复习",
    "加强练习",
    "粗心大意",
    "太粗心",
    "粗心了",
    "粗心",
    "马虎大意",
    "马虎了",
    "马虎",
    "大意了",
    "大意",
    "不知道",
    "不会做",
    "不会",
    "不懂",
    "忘了",
    "忘记了",
    "没看清",
    "没看懂",
    "看错了",
    "算错了",
    "写错了",
    "做错了",
    "蒙错了",
    "乱写的",
    "随便",
    "哈哈",
    "呵呵",
    "测试",
    "略",
)


def format_structured_reflection_note(stuck_point: str, fix_strategy: str) -> str:
    """将双栏复盘编码为结构化文本存储于 SchoolExamItem.error_note。"""
    return f"【失分卡点】{stuck_point.strip()}\n【改进对策】{fix_strategy.strip()}"


def format_returned_reflection_note(reason: str, previous_note: str | None) -> str:
    """为退回重写的复盘添加退回标记，同时保留学生原有文本便于修改深化。"""
    cleaned_prev = re.sub(r"^【退回重写：[^\n】]*】\s*", "", str(previous_note or "").strip())
    header = f"【退回重写：{reason.strip()}】"
    return f"{header}\n{cleaned_prev}" if cleaned_prev else header


def parse_structured_reflection_note(
    error_note: str | None,
    error_category: str | None,
    *,
    is_lost: bool,
) -> dict[str, Any]:
    """无损解析结构化复盘备注与退回状态，兼容历史纯文本备注。"""
    if not is_lost:
        return {
            "reflection_status": "not_required",
            "stuck_point": "",
            "fix_strategy": "",
            "return_reason": None,
        }

    raw = str(error_note or "").strip()
    return_reason: str | None = None
    m_ret = re.match(r"^【退回重写：([^\n】]+)】\s*(.*)$", raw, flags=re.DOTALL)
    body = raw
    if m_ret:
        return_reason = m_ret.group(1).strip() or "请进一步完善复盘"
        body = m_ret.group(2).strip()

    stuck_point = ""
    fix_strategy = ""
    m_struct = re.search(r"【失分卡点】\s*(.*?)\s*【改进对策】\s*(.*)$", body, flags=re.DOTALL)
    if m_struct:
        stuck_point = m_struct.group(1).strip()
        fix_strategy = m_struct.group(2).strip()
    elif body:
        stuck_point = body

    if return_reason is not None:
        status = "needs_revision"
    elif error_category and (stuck_point or fix_strategy):
        status = "completed"
    else:
        status = "pending"

    return {
        "reflection_status": status,
        "stuck_point": stuck_point,
        "fix_strategy": fix_strategy,
        "return_reason": return_reason,
    }


_REFLECTION_STARTER_FRAGMENTS: tuple[str, ...] = (
    "条件我没用上，当时以为",
    "辅助线/解题切入点选错了，应该从",
    "圈出来，确认满足条件再往下算",
    "说明/单位/验根，导致扣分",
    "这一步卡住了，没想到要先",
    "当时心态有点急，跳过",
    "公式时忘记了前提条件",
    "做到这题时时间只剩",
    "答题格式不完整，少了",
    "移项/去括号时",
    "写完这一步后，我用",
    "混了，其实应该是",
    "条件我没用上",
    "的方法检查一遍",
    "这一步，我把",
    "的符号写反了",
    "这一步推导",
    "如果再看到",
    "来不及检查",
    "题目里的",
    "我就先",
    "直接写了",
    "这步漏写了",
    "看成了",
    "概念和",
    "算成了",
    "做到",
    "入手",
    "先把",
)


def _strip_starter_fragments(text: str) -> str:
    """剔除学生端句式起头固定模板外壳，确保仅点击起头不补全时无法过线。"""
    cleaned = text or ""
    for frag in sorted(_REFLECTION_STARTER_FRAGMENTS, key=len, reverse=True):
        cleaned = cleaned.replace(frag, "")
    return cleaned


def _extract_effective_chars(text: str) -> str:
    """仅保留中文字符与英文字母（剥离空白、标点、纯数字），用于真实语义长度统计。"""
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z]", text or ""))


def _strip_perfunctory_cliches(text: str) -> str:
    """剔除句式起头外壳与敷衍套话词库，检验剩余实质内容长度。"""
    cleaned = _strip_starter_fragments(text)
    for phrase in sorted(_PERFUNCTORY_CLICHES, key=len, reverse=True):
        cleaned = cleaned.replace(phrase, "")
    return _extract_effective_chars(cleaned)


def validate_reflection_not_perfunctory(
    stuck_point: str,
    fix_strategy: str,
) -> str | None:
    """第二层本地反敷衍硬规则校验；不通过时返回书童追问口吻提示，通过返回 None。"""
    stuck = (stuck_point or "").strip()
    fix = (fix_strategy or "").strip()

    stuck_eff = _extract_effective_chars(_strip_starter_fragments(stuck))
    fix_eff = _extract_effective_chars(_strip_starter_fragments(fix))

    if len(stuck_eff) < 8:
        return "能再具体说说当时卡在哪一步、或者漏掉了哪个条件吗？（还需再补充几句具体细节）"
    if len(fix_eff) < 8:
        return "给下次的自己留一句具体的提醒吧：遇到这类题先做什么、或者用什么方法检查？"
    if len(stuck_eff) + len(fix_eff) < 20:
        return "还差一点点细节，再多写几句关键条件或检查动作，下次遇到就能稳稳拿分啦。"

    if stuck_eff.lower() == fix_eff.lower():
        return "“当时卡在哪”和“下次怎么提醒自己”别写一模一样的哦，分开说说原因和办法。"

    for label, raw, eff in (("这一步卡点", stuck, stuck_eff), ("给下次的提醒", fix, fix_eff)):
        if re.search(r"(.)\1{3,}", re.sub(r"\s+", "", raw)):
            return f"「{label}」好像出现了连续重复的字符，用自己的话再写清楚一点吧。"
        unique_chars = set(eff.lower())
        if len(unique_chars) < 5:
            return f"「{label}」用字太重复啦，试着写一句完整的话说明白。"
        max_freq = max(eff.lower().count(ch) for ch in unique_chars)
        if max_freq / len(eff) > 0.45:
            return f"「{label}」有不少重复字符，再补充一点真实的思考过程吧。"

    # 剥离敷衍套话后剩余实质分析字符校验
    meaningful_stuck = _strip_perfunctory_cliches(stuck)
    meaningful_fix = _strip_perfunctory_cliches(fix)
    if len(meaningful_stuck) < 5:
        return "先别只怪“粗心/没看清”，试着写明是哪一个条件、符号或步骤出了偏差？"
    if len(meaningful_fix) < 5:
        return "“下次注意”容易忘，换成“如果看到…我就先…”的具体动作会更管用哦。"
    return None


def audit_reflection_with_deepseek(
    *,
    subject: str,
    topic: str,
    question_label: str,
    stem_excerpt: str | None,
    error_category: str,
    stuck_point: str,
    fix_strategy: str,
) -> tuple[bool, str | None, str]:
    """第三层 AI 语义把关：审阅学生复盘是否具体、有针对性；未配置或超时时优雅回退本地严规。"""
    cfg = load_vision_config(require_key=False)
    if cfg is None:
        return True, None, "local_rules"

    subject_cn = _SUBJECT_CN.get(subject, subject)
    stem_info = f"\n题目摘要：{stem_excerpt[:240]}" if stem_excerpt else ""
    prompt = (
        f"你是一位严格但友善的初中【{subject_cn}】老师，正在把关学生提交的校考错题复盘，防止敷衍了事。\n"
        f"题号：{question_label}｜考点：{topic}｜学生所选错因：{error_category}{stem_info}\n"
        f"学生填写的【失分卡点】：{stuck_point}\n"
        f"学生填写的【改进对策】：{fix_strategy}\n\n"
        "判断标准：只要学生具体提到了本题的某个条件、概念、步骤、公式、语法点、文本细节或可执行的检验动作，即可判为通过（passed=true）；"
        "只有当内容明显空洞敷衍（例如只堆砌套话、胡言乱语、与学科/做题完全无关、或完全没有可执行的改进方法）时，才判为不通过（passed=false）。\n"
        "只输出严格 JSON 对象：{\"passed\": true/false, \"coach_feedback\": \"若不通过，用35字以内温和追问1个具体问题引导补充；若通过留空字符串\"}。"
    )
    try:
        data = _post_deepseek_json(
            cfg,
            model=cfg.text_model,
            messages=[
                {"role": "system", "content": "你是初中学习复盘质检老师，只输出严格 JSON 对象。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
        )
        passed = bool(data.get("passed", True))
        feedback = str(data.get("coach_feedback") or "").strip()[:180] or None
        if not passed and not feedback:
            feedback = "请再补充一句：本题具体卡在哪一个条件或步骤，下次用什么办法检查避免？"
        return passed, feedback, cfg.text_model
    except VisionParserUnavailableError:
        return True, None, "local_rules_fallback"
