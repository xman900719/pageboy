# 四科语料增量（迁移 0006）

范围仅限语文、数学、英语、物理。本文只描述已实现并经测试的能力，未实现项见末尾。

## 数据模型

- `source_documents` 新增 `source_class`（official_exam / aux_book / adapted / school / ai / unclassified）、`sha256`、`ingest_status`（采录）、`review_status`（审核）、`paper_key`；采录覆盖与质量审核是两个独立状态。
- `errata` 只追加勘误；`question_source_regions` 记录题目到原件页码/区域；原始题目内容不被修改，更正走既有“修订新版本”或勘误。
- `knowledge_nodes`（稳定 id、层级、状态 active/deprecated/merged）+ `knowledge_node_versions`（名称/描述版本）+ `question_knowledge_links`（题/小问、core/aux、证据、审核状态，并记录关联时的知识点版本）。停用/合并不改写既有关联行。
- `research_runs` 保存研究范围、规则版本、输出与审核状态。

## 规则

- `official_exam` 来源拒绝区县卷（`DISTRICT_PAPER_REJECTED`）与第三方逐题解析（`THIRD_PARTY_ANALYSIS_NOT_OFFICIAL`）。
- 覆盖报告（`GET /api/admin/coverage`）只统计 `official_exam`；状态 missing → recorded → ingested → reviewed。`missing` 仅表示数据库未登记，**不代表本地没有已采录 PDF**；`recorded` 仅表示数据库存在来源记录，**不代表已上传原件**；`ingested` 需要题目入库，`reviewed` 还需题目有效发布和来源审核。
- 来源级 `sha256` 不是调用方自证：新建来源时若提交 `sha256`，返回 `422 SOURCE_HASH_REQUIRES_ATTACHMENT_UPLOAD`；首次成功上传附件时由服务端从文件字节生成，后续附件分别保存自身哈希，不覆写来源的首次附件哈希。覆盖报告的重复哈希检测仅使用已上传附件的服务端计算值；历史无附件的手填值不作为原件证据。上传不自动将 `ingest_status` 改为 `ingested`。
- 命题统计/预测/回测只使用 `official_exam` 且关联已审核的数据；预测第 Y 年只用 <Y 的数据；少于 2 个历史年份输出 `insufficient_evidence`，不虚构命中率；AI 推理标记 BLOCKED（无授权模型接口）。
- `scripts/audit_exam_corpus.py` 只读扫描真题目录并真实计算 SHA256，不复制不修改原件。

## 已实现与未实现边界

- 已实现：81 个北京市新课标四科知识点播种（`shutong/corpus/taxonomy.py`）、2018–2025 连续 8 年 × 4 科 = 32 套北京中考真题（350 道精校试题）与对应的 32 份真题原件附件（28 份 PDF + 2024 年 4 份 DOCX）幂等入库（`scripts/seed_real_corpus.py`）。
- 未实现：AI 模型自动推理（无授权模型接口时保持 BLOCKED）。

## 已采录原件与应用导入的界限（2018–2025 年）

本地真题库（`/media/xc/backup_ntfs/中考题库/北京中考真题-富尔题库`）包含 2018–2025 连续 8 个年份的四科官方空白卷原件（其中 22 份为 `.docx`，10 份为 `.doc` 无损转换生成的标准 `.docx`）。同时包含 47 份教研解析卷，作为 `aux_book` 来源资产与名师精析储备。原件存在、来源真实性审核、附件进入私有存储、题目切分入库、题目人工审核发布是不同里程碑，不能仅凭文件存在将 `/coverage` 直接改为 `ingested` 或 `reviewed`。

私有附件上传限制支持单文件最多 35 MiB、PDF 最多 40 页，支持 `.docx` 原生校验与段落/表格/内嵌 MathType OLE 公式提取，并对含有扫描水印/条码/单行页眉的伪文本层 PDF 自动回退至逐页 OCR。通过 `scripts/seed_real_corpus.py` 可将 2018–2025 年全部 32 套四科真题原件附件、来源审核、已审核发布试题及课标考点关联完整幂等灌入数据库，使 `/api/admin/coverage?year_from=2018&year_to=2025` 中连续 8 个年份的四科全部达到 `reviewed` 状态（`gaps: []`）。
