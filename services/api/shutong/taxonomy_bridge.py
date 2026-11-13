# -*- coding: utf-8 -*-
"""知识体系契约加载、新旧考点桥接、选学过滤与知识图谱前置关系边定义。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# 四科核心前置依赖与关联边（source -> target 表示 source 为 target 的前置基础或直接支撑）
# 所有编码均严格校验存在于 contracts/{subject}_knowledge_taxonomy_candidate.json。
PREREQUISITE_EDGES: dict[str, list[tuple[str, str, str]]] = {
    "math": [
        ("math_cand.num.rational", "math_cand.num.real", "前置基础"),
        ("math_cand.num.real", "math_cand.alg.poly", "运算衔接"),
        ("math_cand.alg.poly", "math_cand.alg.factor", "互逆变形"),
        ("math_cand.alg.factor", "math_cand.alg.frac", "约分通分支撑"),
        ("math_cand.num.real", "math_cand.alg.quadratic_radical", "算术平方根支撑"),
        ("math_cand.alg.poly", "math_cand.eq.linear", "等式变形支撑"),
        ("math_cand.eq.linear", "math_cand.eq.linear_system", "消元转化"),
        ("math_cand.eq.linear", "math_cand.ineq.linear", "同解变形类比"),
        ("math_cand.alg.factor", "math_cand.eq.quadratic", "因式分解解法"),
        ("math_cand.alg.frac", "math_cand.eq.fractional", "分式化简与验根"),
        ("math_cand.eq.linear", "math_cand.func.linear", "方程与函数交点"),
        ("math_cand.geo.coordinates", "math_cand.func.basic", "数形结合基础"),
        ("math_cand.func.basic", "math_cand.func.linear", "函数概念支撑"),
        ("math_cand.func.linear", "math_cand.func.inverse", "解析式研究方法"),
        ("math_cand.eq.quadratic", "math_cand.func.quadratic", "抛物线与一元二次方程"),
        ("math_cand.geo.lines_angles", "math_cand.geo.triangle_basic", "角关系推导"),
        ("math_cand.geo.triangle_basic", "math_cand.geo.congruent_triangles", "全等判定支撑"),
        ("math_cand.geo.congruent_triangles", "math_cand.geo.isosceles_triangle", "性质证明支撑"),
        ("math_cand.geo.triangle_basic", "math_cand.geo.pythagoras", "直角三角形关系"),
        ("math_cand.geo.congruent_triangles", "math_cand.geo.quadrilateral_basic", "对边对角证明"),
        ("math_cand.geo.quadrilateral_basic", "math_cand.geo.special_parallelogram", "特殊化判定"),
        ("math_cand.geo.pythagoras", "math_cand.geo.circle_basic", "垂径定理计算"),
        ("math_cand.geo.circle_basic", "math_cand.geo.circle_tangent", "圆心距与切线判定"),
        ("math_cand.geo.circle_basic", "math_cand.geo.arc_sector", "圆心角弧长换算"),
        ("math_cand.geo.congruent_triangles", "math_cand.geo.similarity", "全等到相似扩展"),
        ("math_cand.geo.similarity", "math_cand.geo.trigonometry", "比值与三角函数"),
        ("math_cand.geo.coordinates", "math_cand.geo.transform_symmetry", "坐标对称变换"),
        ("math_cand.stat.sampling_collection", "math_cand.stat.central_dispersion", "数据整理后分析"),
        ("math_cand.stat.sampling_collection", "math_cand.prob.probability", "频率估计概率"),
        ("math_cand.func.quadratic", "math_cand.prac.exploration_new_definition", "综合探究应用"),
    ],
    "chinese": [
        ("chinese_cand.base.phonetics", "chinese_cand.base.character_orthography", "音形辨析协同"),
        ("chinese_cand.base.character_orthography", "chinese_cand.base.idiom_vocabulary", "词语准确运用"),
        ("chinese_cand.base.syntax_revision", "chinese_cand.base.punctuation", "句法与标点协同"),
        ("chinese_cand.base.idiom_vocabulary", "chinese_cand.base.contextual_expression", "语境表达支撑"),
        ("chinese_cand.prose.classical_vocab", "chinese_cand.prose.classical_syntax_trans", "实词虚词支撑断句翻译"),
        ("chinese_cand.prose.classical_syntax_trans", "chinese_cand.prose.classical_comprehension", "译读支撑文意探究"),
        ("chinese_cand.poetry.dictation", "chinese_cand.poetry.appreciation", "名句积累支撑意象鉴赏"),
        ("chinese_cand.reading.informative_skills", "chinese_cand.reading.multimodal_non_continuous", "说明信息整合延伸"),
        ("chinese_cand.reading.narrative_plot_character", "chinese_cand.reading.narrative_language_theme", "情节人物支撑主旨"),
        ("chinese_cand.reading.argument_claims_evidence", "chinese_cand.reading.argument_methods_structure", "论点论据支撑论证结构"),
        ("chinese_cand.reading.narrative_language_theme", "chinese_cand.writing.composition_narrative", "以读促写借鉴"),
        ("chinese_cand.reading.argument_methods_structure", "chinese_cand.writing.critical_micro_writing", "思辨论证迁移"),
    ],
    "english": [
        ("english_cand.vocab.formation", "english_cand.vocab.collocation_context", "构词扩展语境辨析"),
        ("english_cand.noun.number_case", "english_cand.article.rules", "名词数与冠词协同"),
        ("english_cand.pronoun.types", "english_cand.clause.simple_sentences", "主宾格与简单句"),
        ("english_cand.tense.present_past", "english_cand.tense.future_continuous", "时态体系递进"),
        ("english_cand.tense.present_past", "english_cand.tense.present_perfect", "过去时与现在完成时对比"),
        ("english_cand.tense.present_perfect", "english_cand.voice.passive", "过去分词与被动语态"),
        ("english_cand.clause.simple_sentences", "english_cand.syntax.compound_conjunction", "简单句到并列句"),
        ("english_cand.clause.simple_sentences", "english_cand.syntax.object_clause", "陈述语序基础"),
        ("english_cand.syntax.compound_conjunction", "english_cand.syntax.adverbial_clause", "从属连词扩展"),
        ("english_cand.vocab.collocation_context", "english_cand.reading.facts_inference", "词汇语境支撑阅读"),
        ("english_cand.reading.facts_inference", "english_cand.reading.task_based", "信息定位与整合"),
        ("english_cand.syntax.object_clause", "english_cand.writing.composition", "复合句提升书面表达"),
    ],
    "physics": [
        ("physics_cand.exp.measuring_skills", "physics_cand.motion.speed", "长度时间测量支撑速度"),
        ("physics_cand.exp.measuring_skills", "physics_cand.matter.density_prop", "质量体积测量支撑密度"),
        ("physics_cand.light.propagate_reflect", "physics_cand.light.refract_dispersion", "光路规律递进"),
        ("physics_cand.light.refract_dispersion", "physics_cand.light.lens_application", "折射规律支撑透镜成像"),
        ("physics_cand.force.basics", "physics_cand.force.gravity_friction", "受力分析基础"),
        ("physics_cand.force.gravity_friction", "physics_cand.force.newton_balance", "平衡态受力分析"),
        ("physics_cand.matter.density_prop", "physics_cand.force.pressure_fluid", "密度与液体压强"),
        ("physics_cand.force.pressure_fluid", "physics_cand.force.buoyancy", "压强差与阿基米德原理"),
        ("physics_cand.force.newton_balance", "physics_cand.force.simple_machine", "力臂与平衡条件"),
        ("physics_cand.force.simple_machine", "physics_cand.energy.work_power_eff", "机械做功与效率"),
        ("physics_cand.energy.transfer_concept", "physics_cand.energy.mech_energy_conserv", "能量转化与守恒"),
        ("physics_cand.matter.thermal_state", "physics_cand.energy.internal_heat", "物态吸放热与比热容"),
        ("physics_cand.energy.internal_heat", "physics_cand.energy.heat_engine", "内能利用与热机"),
        ("physics_cand.elec.charge_field", "physics_cand.energy.circuit_rules", "电荷与电流电路"),
        ("physics_cand.energy.circuit_rules", "physics_cand.energy.ohm_law", "电表与变阻器支撑欧姆定律"),
        ("physics_cand.energy.ohm_law", "physics_cand.energy.electric_power_joule", "欧姆定律支撑电功率"),
        ("physics_cand.elec.charge_field", "physics_cand.elec.electromagnetism", "磁场支撑电磁感应"),
        ("physics_cand.exp.inquiry_methods", "physics_cand.energy.ohm_law", "控制变量法探究电流电压电阻"),
    ],
}


def repo_path(relative_path: str) -> Path:
    """解析仓库内相对路径，兼容测试工作目录与容器部署路径。"""
    p = Path(relative_path)
    if p.exists():
        return p
    return Path(__file__).resolve().parents[3] / relative_path


@lru_cache(maxsize=8)
def load_candidate_contracts(subject: str) -> list[dict[str, Any]]:
    """读取指定学科的权威候选知识点契约列表。"""
    p = repo_path(f"contracts/{subject}_knowledge_taxonomy_candidate.json")
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def load_legacy_mappings(subject: str) -> dict[str, list[str]]:
    """加载旧考点编码到新课标候选编码的映射表，自动剥离选学节点。"""
    p = repo_path(f"contracts/{subject}_legacy_taxonomy_mapping.json")
    if not p.is_file():
        return {}
    candidates = {c["code"]: c for c in load_candidate_contracts(subject)}
    elective_codes = {code for code, item in candidates.items() if item.get("is_elective")}
    data = json.loads(p.read_text(encoding="utf-8"))
    mapping: dict[str, list[str]] = {}
    for row in data.get("legacy_mappings", []):
        legacy_code = row.get("legacy_code")
        targets = [
            t for t in (row.get("target_candidate_codes") or [])
            if t not in elective_codes
        ]
        if legacy_code and targets:
            mapping[legacy_code] = targets
    return mapping


def get_elective_codes(subject: str) -> set[str]:
    """返回指定学科被标为选学（*不作考试要求）的知识点编码集合。"""
    return {
        c["code"]
        for c in load_candidate_contracts(subject)
        if c.get("is_elective")
    }


def resolve_question_to_candidate_codes(subject: str, raw_codes: list[str] | None) -> list[str]:
    """将题目的知识点编码（含历史 81 旧码或新候选码）安全映射为非选学的当前体系编码。"""
    if not raw_codes:
        return []
    candidates = {c["code"]: c for c in load_candidate_contracts(subject)}
    elective_codes = {code for code, item in candidates.items() if item.get("is_elective")}
    legacy_map = load_legacy_mappings(subject)
    prefix = f"{subject}_cand."
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in raw_codes:
        if raw in elective_codes:
            continue
        if raw.startswith(prefix) and raw in candidates:
            targets = [raw]
        elif raw in legacy_map:
            targets = legacy_map[raw]
        else:
            targets = []
        for t in targets:
            if t not in elective_codes and t not in seen:
                seen.add(t)
                resolved.append(t)
    return resolved


def get_prerequisite_edges(subject: str, valid_codes: set[str] | None = None) -> list[dict[str, str]]:
    """返回过滤后的前置/关联关系边列表，确保端点均为当前有效非选学节点。"""
    elective_codes = get_elective_codes(subject)
    edges = []
    for src, dst, relation in PREREQUISITE_EDGES.get(subject, []):
        if src in elective_codes or dst in elective_codes:
            continue
        if valid_codes is not None and (src not in valid_codes or dst not in valid_codes):
            continue
        edges.append({"source": src, "target": dst, "relation": relation, "edge_type": "prerequisite"})
    return edges
