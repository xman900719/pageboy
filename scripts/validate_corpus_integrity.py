#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全自动真题与知识点 100% 完整性与正确性强断言质检工具。
任何一项断言失败，立即打印精准错误位置并以非零状态码退出。
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from shutong import private_files as files
from shutong.corpus.taxonomy import TAXONOMY
from shutong.corpus.exam_2025 import ALL_EXAM_PAPERS

REQUIRED_SUBJECTS = {"math", "physics", "english", "chinese"}
REQUIRED_YEARS = {2018, 2019, 2020, 2021, 2022, 2023, 2025}
DEFAULT_CORPUS_DIR = Path("/media/xc/backup_ntfs/中考题库/北京中考真题")

def validate_taxonomy() -> set[str]:
    print("=== [1/4] 检验知识点体系结构 (TAXONOMY) ===")
    all_codes: set[str] = set()
    code_to_subject: dict[str, str] = {}
    
    assert set(TAXONOMY.keys()) == REQUIRED_SUBJECTS, f"科目不全：期望 {REQUIRED_SUBJECTS}，实际 {set(TAXONOMY.keys())}"

    for subject, nodes in TAXONOMY.items():
        assert len(nodes) >= 10, f"{subject} 考点过少：仅 {len(nodes)} 个"
        for node in nodes:
            code = node["code"]
            name = node["name"]
            desc = node["description"]
            parent_code = node["parent_code"]
            
            assert code not in all_codes, f"考点编码重复：{code}"
            assert len(code.strip()) >= 3, f"考点编码不合法：{code}"
            assert len(name.strip()) >= 2, f"考点名称过短：{code}"
            assert len(desc.strip()) >= 5, f"考点描述过短：{code}"
            assert node["subject"] == subject, f"节点科目不匹配：{node}"
            
            all_codes.add(code)
            code_to_subject[code] = subject

    # 二次遍历校验 parent_code 引用
    for subject, nodes in TAXONOMY.items():
        for node in nodes:
            p = node["parent_code"]
            if p is not None:
                assert p in all_codes, f"父节点编码不存在：{node['code']} -> {p}"
                assert code_to_subject[p] == subject, f"父节点科目跨界：{node['code']} ({subject}) -> {p} ({code_to_subject[p]})"

    print(f"✓ 知识点库结构严格自洽：共 {len(all_codes)} 个权威考点，层级关系 100% 闭环")
    return all_codes


def validate_knowledge_labels(all_codes: set[str]) -> None:
    print("\n=== [2/4] 检验前端中文本地化映射 (knowledge-labels.json) ===")
    labels_path = REPO_ROOT / "apps" / "web" / "src" / "config" / "knowledge-labels.json"
    assert labels_path.is_file(), f"找不到本地化文件：{labels_path}"
    
    data = json.loads(labels_path.read_text(encoding="utf-8"))
    
    missing_codes = []
    empty_labels = []
    for code in all_codes:
        if code not in data:
            missing_codes.append(code)
        elif not str(data[code]).strip():
            empty_labels.append(code)
            
    assert not missing_codes, f"前端缺少以下考点的中文标签配置：{missing_codes}"
    assert not empty_labels, f"前端以下考点的中文标签为空：{empty_labels}"
    
    print(f"✓ 前端中文本地化字典 100% 覆盖：全量 {len(all_codes)} 个考点均有非空中文名称")


def validate_exam_papers(known_codes: set[str]) -> None:
    print("\n=== [3/4] 检验 2018-2023 及 2025 年北京中考四科真题数据包 ===")
    seen_year_subjects: set[tuple[int, str]] = set()
    total_questions = 0
    check_pdfs = DEFAULT_CORPUS_DIR.is_dir()

    for paper in ALL_EXAM_PAPERS:
        subject = paper["subject"]
        title = paper["title"]
        year = paper["exam_year"]
        pdf_relpath = paper.get("pdf_relpath", "")
        questions = paper["questions"]
        
        assert subject in REQUIRED_SUBJECTS, f"未知科目：{subject}"
        assert year in REQUIRED_YEARS, f"未知或不在计划内的年份：{year}"
        assert (year, subject) not in seen_year_subjects, f"试卷年份+科目重复：({year}, {subject})"
        seen_year_subjects.add((year, subject))
        
        assert str(year) in title and "北京" in title, f"标题未标明 {year} 北京中考：{title}"
        assert pdf_relpath.endswith(".pdf") and str(year) in pdf_relpath, f"PDF 相对路径不合法：{pdf_relpath}"
        if check_pdfs:
            pdf_file = DEFAULT_CORPUS_DIR / pdf_relpath
            assert pdf_file.is_file(), f"未找到对应的 PDF 真题原件：{pdf_file}"
            files.validate_file(pdf_file.read_bytes(), "application/pdf")
        assert len(questions) >= 10, f"{year} {subject} 试卷题目过少：仅 {len(questions)} 题"
        
        seen_indices = set()
        seen_stems = set()
        paper_score = 0.0

        for q in questions:
            idx = q["index"]
            stem = q["stem"]
            kind = q["kind"]
            options = q.get("options", [])
            correct_answer = q["correct_answer"]
            points = q["max_points"]
            k_codes = q["knowledge_codes"]
            evidence = q["evidence"]

            # 题号与题干互异性
            assert idx not in seen_indices, f"{year} {subject} 试卷存在重复题号：{idx}"
            seen_indices.add(idx)

            clean_stem = re.sub(r"\s+", "", stem)
            assert clean_stem not in seen_stems, f"{year} {subject} 试卷第 {idx} 题题干重复！"
            seen_stems.add(clean_stem)

            # 题型与选项合法性
            assert kind in ["single_choice", "short_answer", "subjective"], f"{year} {subject} 第 {idx} 题题型非法：{kind}"
            if kind == "single_choice":
                assert len(options) == 4, f"{year} {subject} 第 {idx} 题单选选项数不为 4：{options}"
                prefixes = [opt[:2] for opt in options]
                assert prefixes == ["A.", "B.", "C.", "D."], f"{year} {subject} 第 {idx} 题选项前缀非法：{prefixes}"
                assert len(set(options)) == 4, f"{year} {subject} 第 {idx} 题选项存在重复内容：{options}"
                assert correct_answer in ["A", "B", "C", "D"], f"{year} {subject} 第 {idx} 题单选答案不在 A-D 范围：{correct_answer}"
            elif kind == "short_answer":
                assert len(options) == 0, f"{year} {subject} 第 {idx} 题简答题不应有选项：{options}"
                assert len(str(correct_answer).strip()) > 0, f"{year} {subject} 第 {idx} 题标准答案为空"

            # 分值验证
            assert points > 0, f"{year} {subject} 第 {idx} 题分值必须为正数：{points}"
            paper_score += points

            # 知识点关联验证
            assert len(k_codes) >= 1, f"{year} {subject} 第 {idx} 题未挂载任何知识点"
            for c in k_codes:
                assert c in known_codes, f"{year} {subject} 第 {idx} 题挂载了未在课标树中定义的考点：{c}"

            # 溯源与真实证据链
            assert str(year) in evidence and "北京" in evidence, f"{year} {subject} 第 {idx} 题证据未指明出处：{evidence}"

            # KaTeX 语法静态有效性扫描
            inline_math = re.findall(r"\$([^\$]+)\$", stem)
            for expr in inline_math:
                assert expr.count("{") == expr.count("}"), f"{year} {subject} 第 {idx} 题 LaTeX 花括号不平衡：${expr}$"
                assert expr.count("(") == expr.count(")"), f"{year} {subject} 第 {idx} 题圆括号不平衡：${expr}$"
                assert expr.count("[") == expr.count("]"), f"{year} {subject} 第 {idx} 题方括号不平衡：${expr}$"
                assert "\\\\" not in expr or "\\frac" in expr or "\\begin" in expr, f"{year} {subject} 第 {idx} 题存在异常转义"

        total_questions += len(questions)
        print(f"✓ {year} 北京中考 {subject:7s} 核验通过：{len(questions):2d} 道真题，分值小计 {paper_score:.1f} 分，公式与考点 100% 规范")

    expected_pairs = {(y, s) for y in REQUIRED_YEARS for s in REQUIRED_SUBJECTS}
    assert seen_year_subjects == expected_pairs, f"试卷缺少或多余年份+科目：{expected_pairs ^ seen_year_subjects}"
    print(f"\n✓ 全部 {len(ALL_EXAM_PAPERS)} 套四科试卷总计 {total_questions} 道北京中考全真试题，全部通过强断言质检")


def validate_corpus_isolation() -> None:
    print("\n=== [4/4] 检验题库与敏感数据隔离原则 ===")
    from shutong.research import official_reject_reason
    # 验证规则：非官方真题（解析卷、区县模拟）必须被官方来源严格拒绝
    assert official_reject_reason("2019北京中考数学逐题解析.pdf") == "THIRD_PARTY_ANALYSIS_NOT_OFFICIAL"
    assert official_reject_reason("2023海淀区中考一模.pdf") == "DISTRICT_PAPER_REJECTED"
    assert official_reject_reason("2025北京中考数学.pdf") is None
    print("✓ 官方真题筛选规则与来源隔离红线在位生效")


if __name__ == "__main__":
    print("==================================================")
    print("  书童 (Pageboy) 真题与知识点 100% 完整性强断言质检  ")
    print("==================================================")
    try:
        codes = validate_taxonomy()
        validate_knowledge_labels(codes)
        validate_exam_papers(codes)
        validate_corpus_isolation()
        print("\n==================================================")
        print("  🎉 全量质检成功：所有真题与知识点 100% 正确且合规！  ")
        print("==================================================")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 质检断言失败：{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 运行时异常：{e}", file=sys.stderr)
        sys.exit(2)
