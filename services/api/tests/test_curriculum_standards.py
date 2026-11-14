# -*- coding: utf-8 -*-
"""书童 ST-019-A 课程标准来源基线与数学样板自动化测试。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from shutong.curriculum_standards import (
    load_curriculum_sources,
    load_curriculum_clauses,
    validate_curriculum_sources,
    validate_candidate_dataset,
    verify_source_integrity,
    SourceStandardMetadata,
    CurriculumClause,
    ReviewStatusEnum,
    SubjectEnum,
    StageEnum,
)
from shutong.corpus.taxonomy import TAXONOMY
from shutong.home import curriculum_standards_dir

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = ROOT / "contracts"


def test_sources_count_and_subjects():
    """测试四科官方课程标准完整登记且学科唯一，发布日期与生效说明准确。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    assert len(sources) == 4
    # 验证四科学科完整性与唯一性断言
    validate_curriculum_sources(sources)

    subjects = {s.subject for s in sources}
    assert subjects == {
        SubjectEnum.CHINESE,
        SubjectEnum.MATH,
        SubjectEnum.ENGLISH,
        SubjectEnum.PHYSICS,
    }

    # 验证官方发布日期与官方生效说明区分
    for s in sources:
        assert s.official_effective_text == "2022年秋季学期开始执行"
        assert s.technical_effective_date == "2022-09-01"
        assert s.effective_date == "2022-09-01"
        assert "技术约定基准日" in s.effective_date_note
        if s.subject in [SubjectEnum.CHINESE, SubjectEnum.ENGLISH, SubjectEnum.PHYSICS]:
            assert s.published_date == "2022-04-21"
        elif s.subject == SubjectEnum.MATH:
            assert s.published_date == "2022-05-10"


def test_math_errata_revision_status():
    """测试数学课程标准明确标记为2022年5月9日修正版。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    math_src = next(s for s in sources if s.subject == SubjectEnum.MATH)

    assert math_src.source_id == "MOE-2022-MATH-ERRATA-20220509"
    assert math_src.is_errata_revision is True
    assert "2022年5月9日" in math_src.version_tag
    assert math_src.doc_number == "教材〔2022〕2号"
    assert math_src.file_sha256 == "1183b95c58a65eaac4c456f2d2b329bbe42f65a6482993edb537e3eaf8baa144"
    assert math_src.byte_size == 40123943
    assert math_src.page_count == 189
    assert math_src.beijing_applicability.applies_2022_curriculum_standard is True
    assert math_src.beijing_applicability.subject_total_points == 100


def test_beijing_applicability_policy_baseline():
    """测试四科中考政策适用性基线登记（京教计〔2023〕44号）。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    for s in sources:
        beijing = s.beijing_applicability
        assert beijing.status == "confirmed"
        assert beijing.policy_doc_number == "京教计〔2023〕44号"
        assert "北京市教育委员会关于深入推进高中阶段学校考试招生改革的实施意见" in beijing.policy_doc_name
        assert 2025 in beijing.applicable_exam_years
        assert 2026 in beijing.applicable_exam_years
        assert beijing.applies_2022_curriculum_standard is True
        if s.subject in [SubjectEnum.CHINESE, SubjectEnum.MATH, SubjectEnum.ENGLISH]:
            assert beijing.subject_total_points == 100
        elif s.subject == SubjectEnum.PHYSICS:
            assert beijing.subject_total_points == 80


def test_clauses_sample_and_dual_pages():
    """测试数学条款样板双页码准确性与引用闭环。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    clauses = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")

    assert len(clauses) >= 8
    # 候选集严格核验（唯一性、学科一致性、状态强约束）
    validate_candidate_dataset(sources, clauses)

    for c in clauses:
        # 学科与学段统一为初中数学
        assert c.subject == SubjectEnum.MATH
        assert c.stage == StageEnum.STAGE4
        # 双页码逻辑：正文物理页码必须 >= 印刷页码
        assert c.pdf_page >= c.print_page
        assert c.print_page >= 53  # 初中部分起始于印刷页 53
        # 未审核状态门禁：默认恒为 pending
        assert c.review_status == ReviewStatusEnum.PENDING
        # 原文不为空且具有足够长度
        assert len(c.raw_text) >= 10
        # 派生要求不为空
        assert len(c.derived_requirement) >= 5

    # 验证公式条款 5：印刷上标原貌与标准化平铺转写清晰区分
    c06 = next(c for c in clauses if "alg_expr:c06" in c.clause_id)
    assert "a²-b²" in c06.raw_text
    assert c06.standardized_text is not None and "a^2-b^2" in c06.standardized_text
    assert c06.collation_note is not None and "等价转写" in c06.collation_note


def test_candidate_dataset_negative_rules():
    """测试候选数据集负例防御：虚假 approved、重复 ID、学科不一致。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    clauses = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")

    # 1. 拦截虚假 approved 状态
    bad_status = copy.deepcopy(clauses)
    bad_status[0].review_status = ReviewStatusEnum.APPROVED
    with pytest.raises(ValueError, match="自动生成候选只能以 pending 状态进入候选数据集"):
        validate_candidate_dataset(sources, bad_status)

    # 2. 拦截重复条款 ID
    bad_dup = copy.deepcopy(clauses)
    bad_dup.append(copy.deepcopy(clauses[0]))
    with pytest.raises(ValueError, match="发现重复条款 ID"):
        validate_candidate_dataset(sources, bad_dup)

    # 3. 拦截条款与来源学科不匹配
    bad_subj = copy.deepcopy(clauses)
    bad_subj[0].subject = SubjectEnum.CHINESE
    with pytest.raises(ValueError, match="与其关联来源学科"):
        validate_candidate_dataset(sources, bad_subj)


def test_elective_content_flagging():
    """测试选学内容（标*）明确标记且不计入中考考试要求。"""
    clauses = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")
    tri_sys = next(c for c in clauses if "三元一次方程组" in c.raw_text)
    assert tri_sys.is_elective is True
    assert tri_sys.clause_number == "④"
    assert "不作为中考考试要求" in tri_sys.derived_requirement


def test_legacy_taxonomy_protection():
    """测试存量 81 个静态考点完整性保护，旧代码未被覆盖或重定义。"""
    total_nodes = sum(len(v) for v in TAXONOMY.values())
    assert total_nodes == 81
    assert len(TAXONOMY["math"]) == 24
    assert len(TAXONOMY["physics"]) == 21
    assert len(TAXONOMY["english"]) == 18
    assert len(TAXONOMY["chinese"]) == 18

    # 验证样板映射的目标节点全部在存量数学考点中存在
    clauses = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")
    legacy_math_codes = {n["code"] for n in TAXONOMY["math"]}
    for c in clauses:
        for mapped in c.legacy_mappings:
            assert mapped in legacy_math_codes


def test_negative_source_validation_errors():
    """负例测试：非法 SHA256、非法文号与非正数页数拦截。"""
    valid_source = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")[0]

    # 1. 非法 SHA256
    with pytest.raises(ValidationError):
        bad_data = valid_source.model_dump()
        bad_data["file_sha256"] = "not_hex_sha256"
        SourceStandardMetadata.model_validate(bad_data)

    # 2. 非法学段
    with pytest.raises(ValidationError):
        bad_data = valid_source.model_dump()
        bad_data["stage_scope"] = ["stage99"]
        SourceStandardMetadata.model_validate(bad_data)

    # 3. 页数为 0
    with pytest.raises(ValidationError):
        bad_data = valid_source.model_dump()
        bad_data["page_count"] = 0
        SourceStandardMetadata.model_validate(bad_data)


def test_negative_clause_page_inversion_error():
    """负例测试：物理页码小于印刷页码（倒挂矛盾）必须被拦截。"""
    valid_clause = load_curriculum_clauses(CONTRACTS_DIR / "curriculum_clauses_math_sample.json")[0]
    bad_clause_data = valid_clause.model_dump()
    bad_clause_data["pdf_page"] = 20
    bad_clause_data["print_page"] = 60

    with pytest.raises(ValueError, match="PDF物理页码 .* 不能小于书籍印刷页码"):
        CurriculumClause.model_validate(bad_clause_data)


def test_fail_closed_missing_raw_file_negative():
    """负例测试：Fail-Closed 门禁下缺失原件必须拦截并记录错误。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    non_existent = Path("/tmp/definitely_missing_standard_file.pdf")
    res = verify_source_integrity(sources[0], non_existent)
    assert res["file_verified"] is False
    assert any("不存在" in err for err in res["errors"])


def test_local_files_sha256_if_downloaded():
    """如果本地私有目录已下载官方文件，校验其实际 SHA256 与字节数。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    local_name_map = {
        "chinese": "义务教育语文课程标准（2022年版）.pdf",
        "math": "义务教育数学课程标准（2022年版）（以此为准2022年5月9日）.pdf",
        "english": "义务教育英语课程标准（2022年版）.pdf",
        "physics": "义务教育物理课程标准（2022年版）.pdf",
    }
    for s in sources:
        fname = local_name_map[s.subject.value]
        fpath = curriculum_standards_dir() / fname
        if fpath.exists():
            ver = verify_source_integrity(s, fpath)
            assert ver["file_verified"] is True
            assert not ver["errors"]


def test_negative_duplicate_subject_missing_discipline():
    """测试负例：重复学科导致缺科时必须抛出 ValueError 并明确提示缺失学科。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    bad_sources = copy.deepcopy(sources)
    dup_math = copy.deepcopy(bad_sources[1])
    dup_math.source_id = "MOE-2022-MATH-DUPLICATE"
    bad_sources[3] = dup_math  # 替换 physics，导致缺失物理
    with pytest.raises(ValueError, match="缺失学科.*physics"):
        validate_curriculum_sources(bad_sources)


def test_negative_duplicate_source_id():
    """测试负例：存在重复来源 ID 时必须拦截。"""
    sources = load_curriculum_sources(CONTRACTS_DIR / "curriculum_sources.json")
    bad_sources = copy.deepcopy(sources)
    bad_sources.append(copy.deepcopy(sources[0]))
    with pytest.raises(ValueError, match="发现重复来源 ID"):
        validate_curriculum_sources(bad_sources)
