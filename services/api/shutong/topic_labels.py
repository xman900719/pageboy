# -*- coding: utf-8 -*-
"""学生端自然语言主题与提升建议映射模块（杜绝内部知识点编码泄露）。"""
from __future__ import annotations

from shutong.corpus.taxonomy import TAXONOMY

# 提取权威四科课标分类树中的自然语言考点名称
TAXONOMY_MAP: dict[str, str] = {
    node["code"]: node["name"]
    for nodes in TAXONOMY.values()
    for node in nodes
    if node.get("code") and node.get("name")
}

# 虚构与测试考点自然语言别名表（确保测试与样例数据亦不暴露内部代号）
SYNTHETIC_MAP: dict[str, str] = {
    "math.arithmetic": "基础算术运算",
    "math.gap": "基础运算与薄弱短板",
    "math.ok": "核心知识达标模块",
    "math.short": "代数综合与简答计算",
    "math.subj": "几何综合与主观探究",
    "math.listen": "听力理解与应用",
    "math.sparse": "拓展提升考点",
    "math.geometry": "几何图形与推理证明",
    "math.addition": "基础加法运算",
    "math.demo.basic": "中考数学基础综合",
    "physics.sound.demo": "声现象综合探究",
    "physics.optics.demo": "光学与成像实验",
    "english.reading.demo": "阅读理解与词汇运用",
    "chinese.reading.demo": "古诗文阅读与文言实词",
}


def get_topic_label(kid: str | None) -> str:
    """将内部知识点代号转换为面向学生的纯正自然语言领域主题名称。"""
    if not kid:
        return "综合学习领域"
    if kid in TAXONOMY_MAP:
        return TAXONOMY_MAP[kid]
    if kid in SYNTHETIC_MAP:
        return SYNTHETIC_MAP[kid]
    # 对未登记考点进行友好中文清洗，严格过滤英文前缀与点号，绝不暴露内部系统代号
    clean = kid.split(".")[-1].replace("_", " ").title()
    return f"{clean}考点"


def get_student_advice(gap_type: str, topic: str, observed_rate: float | None = None, threshold: float | None = None) -> str:
    """生成面向学生的自然语言能力建议。"""
    if gap_type == "INSUFFICIENT_EVIDENCE":
        return f"关于「{topic}」尚无足够的独立新题证据，建议通过阶段诊断进行未见题检测。"
    elif gap_type == "KNOWLEDGE_GAP":
        rate_str = f"（观察作答率 {round(observed_rate * 100, 1)}%）" if observed_rate is not None else ""
        thresh_str = f"规划阈值 {round(threshold * 100, 1)}%" if threshold is not None else "设定阈值"
        return f"在「{topic}」方向上的作答表现{rate_str}低于{thresh_str}，建议加强专项练习与针对性复习。"
    elif gap_type == "NO_CONFIRMED_GAP":
        return f"「{topic}」当前掌握良好，未确认明显短板，建议按计划保持间隔复练以巩固掌握。"
    return f"建议继续巩固「{topic}」相关练习。"
