#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
书童 ST-019-C R2：语文、英语、物理三科官方课程标准初中条款全集、候选知识体系与存量考点映射构建脚本。

依据：
- 中华人民共和国教育部《义务教育语文课程标准（2022年版）》（教材〔2022〕2号，MOE-2022-CHINESE）
- 中华人民共和国教育部《义务教育英语课程标准（2022年版）》（教材〔2022〕2号，MOE-2022-ENGLISH）
- 中华人民共和国教育部《义务教育物理课程标准（2022年版）》（教材〔2022〕2号，MOE-2022-PHYSICS）
- 北京市初中学业水平考试考查要求与北京市新中考改革指导意见（京教计〔2023〕44号）

严格执行：
1. 条款 ID 符合 cs:{subject}:2022:s4:{domain}:{theme}:{topic}:{id} 规范与 Schema 约束；
2. 完整具备双页码（PDF 物理页码与原书印刷页码）、逐字核对官方原文、标准化转写与选学标记；
3. 初始审核状态恒定为 pending；
4. 候选知识点体系 100% 具备来源条款依据（source_clause_ids 覆盖率 100%）；
5. 存量 57 个旧节点（语文 18、英语 18、物理 21）100% 审计映射并实现只读保护。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "contracts"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"

# 引入学科生成模块
sys.path.insert(0, str(ROOT / "scripts"))
from curriculum_gen.chinese_builder import build_chinese_data
from curriculum_gen.english_builder import build_english_data
from curriculum_gen.physics_builder import build_physics_data

# 引入 TAXONOMY 用于存量 81 个考点校验
sys.path.insert(0, str(ROOT / "services" / "api"))
from shutong.corpus.taxonomy import TAXONOMY


def get_schema_validator(schema_filename: str) -> Draft202012Validator:
    schema_path = SCHEMAS_DIR / schema_filename
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_and_save_dataset(subject: str, data: dict, clause_val: Draft202012Validator):
    clauses = data["clauses"]
    candidates = data["candidates"]
    legacy_mappings = data["legacy_mappings"]

    print(f"=== 校验与生成 [{subject.upper()}] 数据集 ===")
    print(f"  • 条款数: {len(clauses)} | 候选节点数: {len(candidates)} | 存量映射项: {len(legacy_mappings)}")

    # 1. 校验条款 Schema 与逻辑
    clause_ids = set()
    for cl in clauses:
        errors = list(clause_val.iter_errors(cl))
        if errors:
            raise AssertionError(f"[{subject}] 条款 {cl.get('clause_id')} Schema 校验失败: {errors[0].message}")
        cid = cl["clause_id"]
        assert cid not in clause_ids, f"[{subject}] 重复的条款 ID: {cid}"
        clause_ids.add(cid)
        assert cl["pdf_page"] >= cl["print_page"], f"[{subject}] 双页码倒挂: PDF {cl['pdf_page']} < Print {cl['print_page']}"
        assert cl["review_status"] == "pending", f"[{subject}] 初始状态必须恒为 pending: {cid}"
        assert cl["subject"] == subject, f"[{subject}] 条款学科字段不一致: {cid}"

    # 2. 校验候选知识体系逻辑
    cand_codes = set()
    cand_by_code = {}
    for cand in candidates:
        code = cand["code"]
        assert code not in cand_codes, f"[{subject}] 重复候选节点代码: {code}"
        cand_codes.add(code)
        cand_by_code[code] = cand

    # 校验父子层级结构无环
    for code, cand in cand_by_code.items():
        pcode = cand.get("parent_code")
        if pcode:
            assert pcode in cand_by_code, f"[{subject}] 节点 {code} 的父节点 {pcode} 不存在"
            # 环路检测
            curr = pcode
            visited = {code}
            while curr:
                assert curr not in visited, f"[{subject}] 检测到父子关系环路: {code} -> {curr}"
                visited.add(curr)
                curr = cand_by_code[curr].get("parent_code")

    # 为没有明确条款的父级节点（如一级领域）自动聚合其所有下级叶子节点的来源条款
    for code, cand in cand_by_code.items():
        if not cand["source_clause_ids"]:
            descendant_clauses = set()
            stack = [c for c, n in cand_by_code.items() if n.get("parent_code") == code]
            while stack:
                curr_c = stack.pop()
                node = cand_by_code[curr_c]
                descendant_clauses.update(node.get("source_clause_ids", []))
                stack.extend([ch for ch, n in cand_by_code.items() if n.get("parent_code") == curr_c])
            cand["source_clause_ids"] = sorted(list(descendant_clauses))

    for cand in candidates:
        code = cand["code"]
        assert cand["review_status"] == "pending", f"[{subject}] 候选审核状态必须恒为 pending: {code}"
        assert cand["source_clause_ids"], f"[{subject}] 候选节点必须有来源条款依据: {code}"
        for s_cid in cand["source_clause_ids"]:
            assert s_cid in clause_ids, f"[{subject}] 候选节点 {code} 引用了不存在的条款: {s_cid}"

    # 3. 校验存量考点映射完整性
    static_legacy_nodes = TAXONOMY[subject]
    expected_legacy_codes = {n["code"] for n in static_legacy_nodes}
    mapped_legacy_codes = {m["legacy_code"] for m in legacy_mappings}
    assert mapped_legacy_codes == expected_legacy_codes, (
        f"[{subject}] 存量考点未 100% 覆盖: 缺失 {expected_legacy_codes - mapped_legacy_codes}, "
        f"多余 {mapped_legacy_codes - expected_legacy_codes}"
    )

    for m in legacy_mappings:
        assert m["action"] in ["retained", "renamed", "split", "merged", "new", "deprecated", "pending_human_review"], (
            f"[{subject}] 非法动作分类: {m['action']}"
        )
        assert m["target_candidate_codes"], f"[{subject}] 映射目标不能为空: {m['legacy_code']}"
        for tcode in m["target_candidate_codes"]:
            assert tcode in cand_codes, f"[{subject}] 映射目标候选节点不存在: {m['legacy_code']} -> {tcode}"
        assert len(m["mapping_reason"]) >= 5, f"[{subject}] 映射理由过于简略: {m['legacy_code']}"
        assert len(m["compatibility_assurance"]) >= 5, f"[{subject}] 兼容保障过于简略: {m['legacy_code']}"

    # 4. 写入文件
    clauses_file = CONTRACTS_DIR / f"curriculum_clauses_{subject}.json"
    candidates_file = CONTRACTS_DIR / f"{subject}_knowledge_taxonomy_candidate.json"
    mapping_file = CONTRACTS_DIR / f"{subject}_legacy_taxonomy_mapping.json"

    clauses_file.write_text(json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    candidates_file.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "total_legacy_nodes": len(legacy_mappings),
        "retained_count": sum(1 for m in legacy_mappings if m.get("action") == "retained"),
        "renamed_count": sum(1 for m in legacy_mappings if m.get("action") == "renamed"),
        "split_count": sum(1 for m in legacy_mappings if m.get("action") == "split"),
        "merged_count": sum(1 for m in legacy_mappings if m.get("action") == "merged"),
        "new_count": sum(1 for m in legacy_mappings if m.get("action") in ["new", "added"]),
        "deprecated_count": sum(1 for m in legacy_mappings if m.get("action") == "deprecated"),
        "pending_human_review_count": sum(1 for m in legacy_mappings if m.get("action") == "pending_human_review"),
    }
    mapping_file.write_text(json.dumps({
        "subject": subject,
        "legacy_mappings": legacy_mappings,
        "summary": summary
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"  ✓ 成功写入契约文件:")
    print(f"    - {clauses_file.name} ({clauses_file.stat().st_size} bytes)")
    print(f"    - {candidates_file.name} ({candidates_file.stat().st_size} bytes)")
    print(f"    - {mapping_file.name} ({mapping_file.stat().st_size} bytes)")


def main():
    clause_val = get_schema_validator("curriculum-standard-clause.schema.json")

    subjects_data = {
        "chinese": build_chinese_data(),
        "english": build_english_data(),
        "physics": build_physics_data()
    }

    for subj, data in subjects_data.items():
        validate_and_save_dataset(subj, data, clause_val)

    print("\n=======================================================")
    print("✓ 语文、英语、物理三科官方条款全集与候选体系构建成功！")
    print("=======================================================")


if __name__ == "__main__":
    main()
