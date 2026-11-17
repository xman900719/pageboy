---
name: school-exam-and-corpus
description: >-
  Use this skill when working on school exam ingestion/autosync (ST-EXAM-AUTOSYNC R1/R2),
  k12100 synchronization, multi-subject school exam report parsing, 2022 curriculum
  standard clauses, or the 135 Beijing Zhongkao candidate knowledge points.
---

# 学校考试同步、多学科报告与四科课标语料开发 SOP

## 1. 学校考试自动同步与报告中心（ST-EXAM-AUTOSYNC R1/R2 + Reports）

### 1.1 五字段卷头与匹配模型红线
- **唯一合法五字段**：`academic_year`（学年度）、`grade`（年级）、`exam_type`（类型，含独立类型「统一练习」）、`subject`（学科，含数学/语文/英语/物理/道德与法治 `ethics`）、`exam_date`（单一日期字段，管理端录入与展示统一为月精度 `YYYY-MM`，无日期阻断建档）。
- **不识别字段**：不提取或回传 `school_name`、`term`、`series_title`。
- **排名与总分门禁**：
  - 本人排名在 PII 清洗前抽取，且必须通过 `rank_ownership` 浏览器/后端归属校验（`verified` 才持久化入库，`unverified` 或他人列表剔除）；学生端接口严禁暴露排名（403），且排名/学校总分绝不折算知识点能力画像（AC-EVI-01）。
  - 逐题得分 `ocr_draft` 未经人工确认（`confirmed_by_user=True`）绝不产生画像证据（AC-EVI-02）。

### 1.2 常用校考与报告脚本
- **扫描与五字段识别管线**：
  ```bash
  PATH="$PWD/.venv/bin:$PATH" python scripts/school_exam_pipeline.py --help
  ```
- **k12100 环境隔离同步**：
  - 配置与会话严格隔离在 `$PAGEBOY_HOME/development/k12100`（`0700` 目录权限，`k12100.env` 为 `0600`），**严禁创建或读取 `~/.config/shutong`**。
  ```bash
  PATH="$PWD/.venv/bin:$PATH" python scripts/k12100_sync.py --help
  ```
- **多学科分析报告册解析与校验**：
  ```bash
  PATH="$PWD/.venv/bin:$PATH" python scripts/parse_school_report.py --help
  PATH="$PWD/.venv/bin:$PATH" python scripts/validate_school_reports.py
  ```

## 2. 四科 2022 课标条款与 135 候选知识点校验

修改 `contracts/curriculum_clauses_*.json`、`contracts/*_taxonomy_candidates_v2022.json` 或真题语料脚本后，必须运行以下完整性审计：
```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/validate_curriculum_standards.py
PATH="$PWD/.venv/bin:$PATH" python scripts/validate_corpus_integrity.py
PATH="$PWD/.venv/bin:$PATH" python scripts/audit_exam_corpus.py
```
- **选学（`*`）隔离红线**：如数学切线长定理（`math_cand.geo.circle_tangent_length`）、三元一次方程组（`math_cand.eq.linear_system_3var`）必须保持 `is_elective: true` 且与必学旧码物理隔离。
- **测试数据政策红线（`AGENTS.md` #14）**：未经 Owner 显式提供 `PAGEBOY_OWNER_TEST_DATA_APPROVED=1` 与 `PAGEBOY_OWNER_APPROVAL_REF`，严禁向开发库注入任何虚构演示题或虚构校考卷。
