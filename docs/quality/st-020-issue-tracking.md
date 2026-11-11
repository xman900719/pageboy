# ST-020 课标审查问题追踪与证据裁决记录 (st-020-issue-tracking.md)

本文档记录 ST-020 课程标准条款与知识库候选审查中发现的问题状态、阶段整改（RM）闭环记录、误报裁决证据，以及累积变更与本轮新增变更的严格边界说明。

---

## 1. 任务状态与整改（RM）闭环汇总

| 整改编号 | 涉及学科 | 关联条款 / 知识点 | 整改核心要点 | 当前状态 | 最终证据依据 |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **ST-020-RM-01** | 数学 | `circle:c01`~`circle:c10` | 修复圆章节条款序号错位、拆分垂径定理 c01b，全集 10 条齐备，必学/选学严格区分 | **`CLOSED`** | `contracts/curriculum_clauses_math.json`<br>`services/api/tests/test_math_taxonomy_st019b.py` |
| **ST-020-RM-02** | 语文 | `vocabulary_req:c03a`<br>`vocabulary:c03` | 增补第(3)条内容要求 c03a，保留校准 c03 教学提示，如实记载逗号与官方分号标点历史差异 | **`CLOSED`** | `/media/xc/backup_ext4/code/ShuTong_ST-020-RM-02_Review_R2.zip`<br>(SHA256: `cef91a3b3b6f110dfba1cfc6ef855da7121c9a6bd147f601d9ce535cad0ac155`) |
| **ST-020-RM-03** | 语文 | `classical_vocab:c28` | 补齐第四学段学段要求第6条末句“背诵优秀诗文80篇（段）。” | **`CLOSED`** | `/media/xc/backup_ext4/code/ShuTong_ST-020-RM-03_Review_R3.zip`<br>(SHA256: `06d5a36ed95a3104f92509dbfd54ad06a63a5dd9b1a0d75e9e74bc3b81f1b021`) |
| **ST-020-2A** | 四科全量 | 全量 312 条款 / 134 候选 | 建立四科条款与候选知识点审核库存台账，完成五级风险分级与三轮 GPT 独立复核及最终证据收口 | **`CLOSED`** | `/media/xc/backup_ext4/code/ShuTong_ST-020-2A_Closeout.md`<br>`/media/xc/backup_ext4/code/ShuTong_ST-020-2A_Audit_Baseline_Review_R3.zip` |
| **ST-020-2B-01** | 数语物 | `math_cand.geo.circle_tangent`<br>16 语文候选/22 语文条款<br>`physics_cand.matter.micro_structure` | 落实三大高风险方向定点整改：数学切线选学隔离（扩至 48 候选）、语文 16 候选与 22 条款幽灵旧码清零（保留微写作等合法跨域映射）、物理密度错配清除为 `[]`，全量测试：222 passed, 25 skipped, 0 failed（耗时 26.79s） | **`CLOSED`** | `/media/xc/backup_ext4/code/ShuTong_ST-020-2B-01_Review_R2.zip`<br>(SHA256: `9041844883fa4305905a7a8370ef944a84faa264226e44b33a5a4feb8cb62660`) |

---

## 2. 累积变更（RM-01/RM-02）与本轮新增变更（RM-03）严格界定

为确保 Review 边界清晰，避免历史累积修改与当前审查目标混淆，特明确以下隔离说明：

### 2.1 RM-01 已验收累积变更（状态：CLOSED，严格锁定）
- **变更文件**：
  - `contracts/curriculum_clauses_math.json`
  - `contracts/math_knowledge_taxonomy_candidate.json`
  - `services/api/tests/test_math_taxonomy_st019b.py`
- **变更属性**：数学圆章节 I-A 整改已于 RM-01 验收闭环，不属于本次 Review 范围。在 RM-03 期间严格保持锁定，零修改。

### 2.2 RM-02 已验收累积变更（状态：CLOSED，严格锁定）
- **变更文件**：
  - `contracts/curriculum_clauses_chinese.json`（仅第 99~139 行：新增 `vocabulary_req:c03a`，校准 `vocabulary:c03` 标点说明）
  - `contracts/chinese_knowledge_taxonomy_candidate.json`（增补两个知识点节点对 `c03a` 的引用）
  - `services/api/tests/test_three_subjects_taxonomy_st019c.py`（新增 `test_chinese_st020_rm02_clause_accuracy_and_schema` 定点测试）
- **验收依据**：Owner 已批准，GPT 第二轮验收通过，最终证据归档于 `/media/xc/backup_ext4/code/ShuTong_ST-020-RM-02_Review_R2.zip`。
- **变更属性**：已闭环存量变更。在 RM-03 中严禁重新修改或推倒重来。

### 2.3 RM-03 本轮独立新增变更（状态：CLOSED，最终验收通过）
- **契约变更**：
  - `contracts/curriculum_clauses_chinese.json`（仅第 735~743 行）：在 `classical_vocab:c28.raw_text` 末尾补齐“背诵优秀诗文80篇（段）。”，并将 `collation_note` 更新为“【ST-020-RM-03 补齐末句】...”。除此 2 处文本外，**未改动契约中的任何其他字符**。
- **知识库候选**：
  - `contracts/chinese_knowledge_taxonomy_candidate.json`：**零修改 (Unchanged)**。
- **测试代码变更**：
  - `services/api/tests/test_three_subjects_taxonomy_st019c.py`（新增 `test_chinese_st020_rm03_classical_vocab_accuracy_and_schema` 定点测试与 ISS-EN-01A 误报保护断言）。
- **文档与追踪**：
  - `docs/quality/st-020-issue-tracking.md`（新建追踪专卷，纳入 Review 包）。
  - `PROJECT_STATUS.md` 与 `task.md`（状态同步）。
- **验收依据**：GPT 第三轮最终定点复核通过，最终验收依据归档于 `/media/xc/backup_ext4/code/ShuTong_ST-020-RM-03_Review_R3.zip`（SHA256: `06d5a36ed95a3104f92509dbfd54ad06a63a5dd9b1a0d75e9e74bc3b81f1b021`）。

---

## 3. 阶段 B：ISS-EN-01A 证据核验与误报更正

### 3.1 问题历史记录
此前 ST-020 早期审核讨论记录中，曾记录一条质疑观点：“声称三级语音要求第六项不存在”（内部登记编号 `ISS-EN-01A`）。

### 3.2 官方原件与 SHA256 独立核验证据
- **官方依据**：中华人民共和国教育部《义务教育英语课程标准（2022年版）》（教材〔2022〕2号）
- **官方下载源**：`http://www.moe.gov.cn/srcsite/A26/s8001/202204/W020220420582349487953.pdf`
- **登记与实际 SHA256**：`59ec3971e0dbd6ca487c4e4972cbc80effaf2fd62418d07e5f62c6698fa222fb`（完全匹配）
- **目标位置**：官方 PDF 第 26 页，书籍印刷第 19 页，`表 9 语音知识内容要求`。
- **三级栏目原文核验**：
  官方原表第 19 页“三级”栏目完整印有 6 项要求：
  1. 了解语音在语言学习中的意义和在语境中的表意功能；
  2. 辨识口语表达中的意群，并在口头交流中按照意群表达；
  3. 根据重音、意群、语调与节奏等语音方面的变化，感知和理解说话人表达的意义、意图和态度；
  4. 借助重音、意群、语调、节奏等方面的变化，表达不同的意义、意图和态度；
  5. 根据读音规则和音标拼读单词；
  6. **查词典时，运用音标知识学习单词的发音。**

### 3.3 当前裁决
1. **裁决为误报**：三级语音要求第 6 项在官方课标原件中**真实、合法且清晰存在**，“声称第六项不存在”属于对课标原件的**误报 (INVALID / FALSE POSITIVE)**。
2. **严格保持现状**：契约 `contracts/curriculum_clauses_english.json` 中 `cs:english:2022:s4:lang_usage:content_req:phonetics:c03.raw_text` 完整且准确包含该第 6 项，**严格不得删除第六项，严格不得修改 `phonetics:c03.raw_text`**。
3. **保留历史溯源**：原有历史审核记录予以保留，本文档作为官方有效证据更正存档，并在测试套件中设置了回归保护断言。

---

## 4. 阶段 C：RM-03 目标（ISS-CH-03B）发现过程与官方证据

### 4.1 发现来源与确认过程声明
> **重要声明**：`ISS-CH-03B` 为 **本轮新发现（NEWLY DISCOVERED IN ST-020-RM-03 STAGE C）**。此前审核清单中并未将文言文阅读末句遗漏登记为正式确认问题，不得冒称此前已确认。

- **发现过程**：
  在按照任务指令执行阶段 C“课标原文完整性排查与范围冻结”时，对官方原件第四学段的各项要求进行逐字通读比对。比对至语文课标印刷第 15 页（PDF 第 22 页）第四学段【阅读与鉴赏】第 6 条时，发现当前契约 `classical_vocab:c28.raw_text` 存在段末截断，且注记声称“与教育部2022版课标第15页原件一致”。经逐字核查证实该遗漏客观存在，故将其正式登记为 `ISS-CH-03B` 并作为 RM-03 唯一整改目标予以冻结。

### 4.2 官方原文证据
- **目标条款 ID**：`cs:chinese:2022:s4:reading:content_req:classical_vocab:c28`
- **官方权威原件**：教育部《义务教育语文课程标准（2022年版）》（教材〔2022〕2号）
- **文件 SHA256**：`3ef0ec8a30b5a950211202658df07d99f5427f750f8ba0c3cfda12736b7bd71a`
- **目标位置**：官方 PDF 第 22 页，书籍印刷第 15 页，三、课程目标 -> （二）学段要求 -> 第四学段（7~9年级） -> 【阅读与鉴赏】第 6 条。
- **官方原件真实全文**：
  > 6. 诵读古代诗词，阅读浅易文言文，能借助注释和工具书理解基本内容。注重积累、感悟和运用，提高自己的欣赏品位。背诵优秀诗文 80 篇（段）。
- **当前契约错误位置与缺陷**：
  `contracts/curriculum_clauses_chinese.json` 中 `classical_vocab:c28.raw_text` 原值为：
  > 诵读古代诗词，阅读浅易文言文，能借助注释和工具书理解基本内容。注重积累、感悟和运用，提高自己的欣赏品位。
  **遗漏了原自然段末句“背诵优秀诗文80篇（段）。”**。
- **定点实施方案**：
  1. 在 `classical_vocab:c28.raw_text` 末尾精准补齐“背诵优秀诗文80篇（段）。”；
  2. 校准 `collation_note` 说明；
  3. 主键、条款类型、其他字段、旧考点映射 100% 保持不变；
  4. 自动化测试套件补充定点测试验证。
