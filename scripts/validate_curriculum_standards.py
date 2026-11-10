#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""书童 ST-019-A 课程标准来源基线与条款定位独立校验脚本。

执行四科国家课程标准来源元数据核查、数学样板条款定位校验、
双页码逻辑核验、未审核状态防篡改校验、Fail-Closed 原件门禁，
以及正反例负例防御断言。
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker

# 将 services/api 加入导入路径
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from shutong.curriculum_standards import (
    calculate_sha256,
    load_curriculum_sources,
    load_curriculum_clauses,
    validate_curriculum_sources,
    validate_candidate_dataset,
    verify_source_integrity,
    SourceStandardMetadata,
    CurriculumClause,
    ReviewStatusEnum,
    SubjectEnum
)
from shutong.corpus.taxonomy import TAXONOMY

SCHEMAS_DIR = ROOT / "contracts" / "schemas"
CONTRACTS_DIR = ROOT / "contracts"
PRIVATE_STANDARDS_DIR = ROOT / "private-data" / "curriculum_standards"


def get_validator(schema_filename: str) -> Draft202012Validator:
    """加载并构建指定 JSON Schema 验证器。"""
    schema_path = SCHEMAS_DIR / schema_filename
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema 文件不存在: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_contracts_and_schema() -> None:
    """1. 严格使用 Draft 2020-12 校验契约文件。"""
    print("[1/5] 校验 JSON Schema 契约合法性...")
    source_val = get_validator("curriculum-standard-source.schema.json")
    clause_val = get_validator("curriculum-standard-clause.schema.json")

    sources_path = CONTRACTS_DIR / "curriculum_sources.json"
    clauses_path = CONTRACTS_DIR / "curriculum_clauses_math_sample.json"

    sources_data = json.loads(sources_path.read_text(encoding="utf-8"))
    clauses_data = json.loads(clauses_path.read_text(encoding="utf-8"))

    # 校验每个来源对象
    for item in sources_data:
        errors = list(source_val.iter_errors(item))
        if errors:
            raise AssertionError(f"来源元数据 Schema 校验失败: {errors[0].message}")
    print(f"  ✓ 四科官方来源清单 ({len(sources_data)} 项) 符合 Schema 契约")

    # 校验数学样板及四科条款全集契约
    for item in clauses_data:
        errors = list(clause_val.iter_errors(item))
        if errors:
            raise AssertionError(f"条款定位 Schema 校验失败: {errors[0].message}")
    print(f"  ✓ 数学样板条款采录 ({len(clauses_data)} 条) 符合 Schema 契约")

    for subj in ["chinese", "math", "english", "physics"]:
        p = CONTRACTS_DIR / f"curriculum_clauses_{subj}.json"
        if p.is_file():
            subj_clauses = json.loads(p.read_text(encoding="utf-8"))
            for item in subj_clauses:
                errors = list(clause_val.iter_errors(item))
                if errors:
                    raise AssertionError(f"[{subj}] 条款 Schema 校验失败: {errors[0].message}")
            print(f"  ✓ {subj} 条款全集采录 ({len(subj_clauses)} 条) 符合 Schema 契约")


def validate_pydantic_and_logic() -> None:
    """2. 执行 Pydantic 模型加载、条款唯一性、学科一致性与业务逻辑核验。"""
    print("[2/5] 校验 Pydantic 模型与交叉引用逻辑...")
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    clauses = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")

    assert len(sources) == 4, f"期望四科官方来源，实际 {len(sources)} 项"
    # 执行四科来源集合完整性与来源 ID 唯一性强校验
    validate_curriculum_sources(sources)

    # 校验数学来源勘误修正版标记
    math_source = next(s for s in sources if s.subject == SubjectEnum.MATH)
    assert math_source.is_errata_revision is True, "数学课标必须明确标记为勘误修正版"
    assert "2022年5月9日" in math_source.version_tag, "数学版本标签必须包含2022年5月9日"
    assert math_source.official_effective_text == "2022年秋季学期开始执行"
    assert math_source.technical_effective_date == "2022-09-01"

    # 执行候选数据集严格核验（条款唯一性、学科一致性、状态恒为 pending、双页码）
    validate_candidate_dataset(sources, clauses)

    # 校验数学样板第 5 条公式原文与标准化表达区分
    formula_clause = next(c for c in clauses if "alg_expr:c06" in c.clause_id)
    assert "a²-b²" in formula_clause.raw_text, "raw_text 必须保留原件印刷上标字符特征"
    assert formula_clause.standardized_text is not None and "a^2-b^2" in formula_clause.standardized_text, "standardized_text 必须提供标准化平铺代数转写"
    assert formula_clause.collation_note is not None and len(formula_clause.collation_note) >= 20, "collation_note 必须提供人工核验比对与转写说明"

    print("  ✓ 来源四科齐备且 ID 唯一，数学 2022-05-09 修正版状态核实通过")
    print(f"  ✓ 全部 {len(clauses)} 条款 ID 唯一、学科一致、双页码合规，第 5 条公式原文与转写清晰区分，候选状态强约束为 pending")


def validate_local_raw_files(allow_unverified: bool = False) -> bool:
    """3. 逐字节核验私有原件哈希与大小；正式验收模式下 Fail-Closed。"""
    print("[3/5] 校验私有原件 SHA256 与文件属性（Fail-Closed 门禁）...")
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")

    local_name_map = {
        "chinese": "义务教育语文课程标准（2022年版）.pdf",
        "math": "义务教育数学课程标准（2022年版）（以此为准2022年5月9日）.pdf",
        "english": "义务教育英语课程标准（2022年版）.pdf",
        "physics": "义务教育物理课程标准（2022年版）.pdf",
    }

    verified_count = 0
    missing_files = []
    mismatched_files = []

    for s in sources:
        expected_filename = local_name_map.get(s.subject.value)
        file_path = PRIVATE_STANDARDS_DIR / expected_filename if expected_filename else None

        if not file_path or not file_path.exists():
            missing_files.append((s.subject.value, expected_filename))
            continue

        ver = verify_source_integrity(s, file_path)
        if ver["file_verified"]:
            verified_count += 1
            print(f"  ✓ [{s.subject.value}] 原件字节数 {s.byte_size} 与 SHA256 {s.file_sha256[:12]}... 严格匹配")
        else:
            mismatched_files.append((s.subject.value, ver["errors"]))

    # 判定门禁
    all_passed = (verified_count == len(sources)) and not missing_files and not mismatched_files

    if not all_passed:
        if allow_unverified:
            print(f"  ! [UNVERIFIED_SOURCE_FILES] 处于开发模式，存在未核验原件 (实到 {verified_count}/{len(sources)})，绝不显示正式验收 PASS")
            return False
        else:
            error_details = []
            if missing_files:
                error_details.append(f"缺失原件文件: {missing_files}")
            if mismatched_files:
                error_details.append(f"原件校验失败: {mismatched_files}")
            raise AssertionError(f"正式验收模式原件核验失败（Fail-Closed 门禁拦截）: {'; '.join(error_details)}")

    print(f"  ✓ 全部四科原件物理文件均已就位并 100% 校验通过")
    return True


def validate_legacy_taxonomy_protection() -> None:
    """4. 确保旧 81 个静态考点不受任何修改或破坏。"""
    print("[4/5] 校验存量 81 个静态考点保护...")
    total_nodes = sum(len(v) for v in TAXONOMY.values())
    assert total_nodes == 81, f"存量考点总数异常: 期望 81, 实际 {total_nodes}"
    assert len(TAXONOMY["math"]) == 24, "数学存量考点应为 24 个"
    assert len(TAXONOMY["physics"]) == 21, "物理存量考点应为 21 个"
    assert len(TAXONOMY["english"]) == 18, "英语存量考点应为 18 个"
    assert len(TAXONOMY["chinese"]) == 18, "语文存量考点应为 18 个"

    # 检查样板映射中的代码是否均为真实存在的旧考点
    clauses = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")
    legacy_math_codes = {n["code"] for n in TAXONOMY["math"]}
    for c in clauses:
        for mapped in c.legacy_mappings:
            assert mapped in legacy_math_codes, f"映射了不存在的旧考点代码: {mapped}"

    print(f"  ✓ 存量 81 个考点树节点结构完整无损，只读映射草案合法")


def run_negative_tests() -> None:
    """5. 执行严格的反例与异常数据拦截防御测试。"""
    print("[5/5] 执行反例与异常数据拦截防御测试...")
    source_val = get_validator("curriculum-standard-source.schema.json")
    clause_val = get_validator("curriculum-standard-clause.schema.json")

    valid_sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    valid_clauses = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")
    valid_source = json.loads((CONTRACTS_DIR / "curriculum_sources.json").read_text(encoding="utf-8"))[0]
    valid_clause = json.loads((CONTRACTS_DIR / "curriculum_clauses_math_sample.json").read_text(encoding="utf-8"))[0]

    # 反例 1：非法 SHA256（非十六进制或长度不等于64）
    bad_sha = copy.deepcopy(valid_source)
    bad_sha["file_sha256"] = "invalid_hash_value"
    assert list(source_val.iter_errors(bad_sha)), "未能成功拦截非法 SHA256"

    # 反例 2：非法来源 URL 格式
    bad_url = copy.deepcopy(valid_source)
    bad_url["source_url"] = "not_a_valid_url"
    assert list(source_val.iter_errors(bad_url)), "未能成功拦截非法 URL"

    # 反例 3：物理页码小于印刷页码（逻辑矛盾）
    bad_page = copy.deepcopy(valid_clause)
    bad_page["pdf_page"] = 10
    bad_page["print_page"] = 50
    try:
        CurriculumClause.model_validate(bad_page)
        raise AssertionError("未能成功拦截 pdf_page < print_page 矛盾")
    except ValueError:
        pass  # 成功拦截

    # 反例 4：AI 虚假 approved 状态（自动生成候选只能以 pending 状态进入候选数据集）
    fake_clauses = copy.deepcopy(valid_clauses)
    fake_clauses[0].review_status = ReviewStatusEnum.APPROVED
    try:
        validate_candidate_dataset(valid_sources, fake_clauses)
        raise AssertionError("未能成功拦截虚假 approved 候选状态")
    except ValueError as e:
        assert "自动生成候选只能以 pending 状态进入候选数据集" in str(e)

    # 反例 5：重复条款 ID 注入
    dup_clauses = copy.deepcopy(valid_clauses)
    dup_clauses.append(copy.deepcopy(valid_clauses[0]))
    try:
        validate_candidate_dataset(valid_sources, dup_clauses)
        raise AssertionError("未能成功拦截重复条款 ID")
    except ValueError as e:
        assert "发现重复条款 ID" in str(e)

    # 反例 6：条款学科与来源学科不一致
    mismatched_subj_clauses = copy.deepcopy(valid_clauses)
    mismatched_subj_clauses[0].subject = SubjectEnum.CHINESE  # 实际对应 MOE-2022-MATH-ERRATA
    try:
        validate_candidate_dataset(valid_sources, mismatched_subj_clauses)
        raise AssertionError("未能成功拦截条款与来源学科不匹配")
    except ValueError as e:
        assert "与其关联来源学科" in str(e)

    # 反例 7：原件缺失导致核验失败 (Fail-Closed 门禁单测)
    non_existent_path = Path("/tmp/non_existent_curriculum_standard.pdf")
    ver_res = verify_source_integrity(valid_sources[0], non_existent_path)
    assert ver_res["file_verified"] is False, "原件缺失时不得判定 file_verified 为 True"
    assert any("不存在" in err for err in ver_res["errors"]), "原件缺失时必须明确记录错误信息"

    # 反例 8：重复学科导致缺科拦截（如用重复的数学来源替换物理来源）
    dup_subj_sources = copy.deepcopy(valid_sources)
    dup_math = copy.deepcopy(dup_subj_sources[1])  # math
    dup_math.source_id = "MOE-2022-MATH-DUPLICATE"
    dup_subj_sources[3] = dup_math  # 替换 physics
    try:
        validate_curriculum_sources(dup_subj_sources)
        raise AssertionError("未能成功拦截重复学科导致缺科")
    except ValueError as e:
        assert "缺失学科" in str(e) and "physics" in str(e)

    # 反例 9：重复来源 ID 拦截
    dup_id_sources = copy.deepcopy(valid_sources)
    dup_id_sources.append(copy.deepcopy(valid_sources[0]))
    try:
        validate_curriculum_sources(dup_id_sources)
        raise AssertionError("未能成功拦截重复来源 ID")
    except ValueError as e:
        assert "发现重复来源 ID" in str(e)

    print("  ✓ 9 项反例与边界防御断言全部成功拦截（含 Fail-Closed 缺失原件、虚假 approved、缺科与重复来源 ID 拦截）")


def main() -> None:
    parser = argparse.ArgumentParser(description="书童 ST-019-A 课程标准来源与条款基线独立校验")
    parser.add_argument("--allow-unverified-files", action="store_true", help="允许无本地原件的开发模式（绝不显示 PASS）")
    args = parser.parse_args()

    print("==================================================")
    print("  书童 ST-019-A 课程标准来源与条款基线全量校验")
    print("==================================================")
    validate_contracts_and_schema()
    validate_pydantic_and_logic()
    files_ok = validate_local_raw_files(allow_unverified=args.allow_unverified_files)
    validate_legacy_taxonomy_protection()
    run_negative_tests()
    print("==================================================")
    if files_ok:
        print("  PASS: 课程标准来源基线与数学样板校验全部通过")
    else:
        print("  DEV_MODE_COMPLETED: UNVERIFIED_SOURCE_FILES (非正式验收)")
        sys.exit(2)
    print("==================================================")


if __name__ == "__main__":
    main()
