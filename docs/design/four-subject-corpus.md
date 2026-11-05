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

## 未实现

知识点内容播种（四份知识要点 PDF 为商业教辅扫描，文本层乱码，目录页 OCR 不可用）、真题切题入库与人工审核、AI 模型推理、前端界面。

## 已采录原件与应用导入的界限（2025 年）

此前本地只读 PDF 审计发现 2025 年语文、数学、英语、物理四科文件；文件级采录已经完成，不重新采集。PDF 文件存在、来源真实性审核、附件进入私有存储、题目切分入库、题目人工审核发布是不同里程碑，不能凭文件存在将 `/coverage` 直接改为 `ingested` 或 `reviewed`。

当前私有附件上传限制 PDF 最多 20 页；此前清单中数学卷 29 页、物理卷 21 页，不满足现有限额。因此这两份本地 PDF 仍只能视为**离线已采录**，不得虚构已完成应用上传/题目入库。已有 `scripts/audit_exam_corpus.py` 允许在原位置只读计算哈希；该审计不能自动写入数据库。调整页数限制和实际真题入库不属于本轮修复。
