# ST-011 验证记录：人工审核 UI（题库审核台）与草稿只读端点

日期：2026-10-26。验收口径：IMPLEMENTATION_PLAN ST-011 行。双通道交付：designer lane（审核台 UI）+ orchestrator lane（后端只读端点与 e2e 旅程）。数据边界不变：e2e 全部旅程数据为 globalSetup 种入或 UI 现场创建的虚构测试数据（临时 SQLite + 临时私有目录）。

## 实现（最小范围）

- **后端（契约补缺）**：审核工作流 API 原先没有任何草稿读取端点（`SourceDetailOut` 只回 `question_version_ids`），审核 UI 无法回显草稿。新增只读端点 `GET /api/admin/sources/{source_id}/questions`（`ingestion.py`，`require_owner` 门禁、按 question_id+version 排序）→ `QuestionVersionOut[]`（12 字段：id/question_id/version/status/reviewed_by_human/stem/kind/options/correct_answer/knowledge_ids/max_points/group_context/media_attachment_id；无存储键、无字节路由）。零数据结构变更，无迁移。
- **审核台 UI（第 4 视图「审核台」）**：题源台账（列表/登记表单/verified 徽章）→ 来源人工审核表单（exam_year/https 链接/获取日期/版权状态/版权依据/适用性；`reviewed_by_human` 为显式勾选门禁，未勾选不能提交）→ 附件区（MIME 与 10MiB 预检上传、sha256/状态、解析、常驻「上传复位已审核」警示）→ 逐题录入确认导入（选项自动编号、显式「我已逐题人工核对」勾选）→ 题目版本列表（draft→人工审核通过→reviewed→发布；来源未审核时发布按钮如实禁用并说明原因，与后端 409 语义一致）。
- **e2e 新增**：J5 审核台全闭环旅程（含两处人工门禁反例断言与发布禁用反例）；A4 审核台 axe 扫描；R1 响应式扩展至四视图。

## 实际命令与结果

- 后端红→绿：新端点 2 项测试先行证实 404/缺失（红），实现后 `tests/test_ingestion.py` 37 passed；API 全量 **112 passed / 25 skipped**（原 110 + 2）。
- 契约：`scripts/generate_openapi.py` 再生成后 `check_openapi.py` PASS（+1 路径 +1 schema，零漂移）。
- `npm run build` → 零错误（tsc -b + vite build）。
- `npx playwright test`（chromium）→ **9 passed + 3 skipped**：A1–A4（A4 审核台 0 违规）、J1–J5 全绿（J5 2.5s）；R1–R3 按设计跳过。
- `npm run test:e2e:ipad`（WebKit + iPad 矩阵）→ **12 passed（30.7s）**：A1–A4、R1–R3、J1–J5 在 WebKit 下全绿。

## 过程记录（如实）

- **读码发现真 bug ×2（designer 汇报之外的实证核查）**：① `ConfirmImportForm` 把 `source_document_id` 填成附件 id——后端按「题目所属题源 == 附件所属题源」校验，必然 409 IMPORT_SOURCE_MISMATCH，designer 探针未覆盖确认导入成功路径（彼时端点在途）；修正为 `attachment.source_document_id`，J5 端到端证明。② `QuestionVersionsCard` 自动重载依赖错误：确认导入令附件转 confirmed 但 attachments/reviews 计数不变，草稿列表保持陈旧——J5 红测试（快照实证「该题源还没有题目版本」）捕获；改为以 `source` 对象引用（AdminView 每次刷新必为新对象）为重载信号后全绿。
- designer lane 自身修过一处真实缺陷：React fragment 子元素逐个 `key={source.id}` 导致切换题源时新旧工作区并存，改为单个 keyed wrapper。
- J5 附件走合成音频路径（ID3 魔数 + 零填充）：CI 的 web-e2e / web-e2e-webkit 作业不装 poppler，音频路径（无转写 → 需人工录入）使旅程无解析器依赖；后端 PDF/图片解析已有 37 项护栏覆盖。

## 限制与未验证

- PDF/图片「解析文本」区块的 UI 呈现未入 J5（本地 API 测试已覆盖解析行为；如需 UI 级验证须先给 web-e2e CI 作业装 poppler）。
- `HOME_EMPTY_PLAN` 中「管理端」措辞与实际功能名（审核台）不完全一致（designer 指出，超 ST-011 范围，遗留备查）。
- 草稿内容（含参考答案）经新端点仅对 owner 令牌可见，与既有私有红线一致；无公开路由。

## 远端 CI 实测

- 推送 `ca0300b`（codex/st-003-private-ingestion）触发 [run 40248302508](https://github.com/xman900719/pageboy/actions/runs/40248302508)（2026-10-26）：**五作业全绿**——api-and-docs 1m31s、web-build 16s、pg-migration 1m9s、web-e2e 1m23s、**web-e2e-webkit 13m58s**（J5/A4 首次远端运行）。
- 作业日志实证：chromium 通道 **9 passed + 3 skipped（25.6s）**、iPad/WebKit 通道 **12 passed（1.8m）**——J5 审核闭环与 A4 扫描在 Runner（Ubuntu 26）一次通过；webkit 作业总时长主要在 `npx playwright install webkit --with-deps` 冷装（apt + 下载），测试本体 1.8m，与既有 Node 20 弃用告警无关。

下一项任务：无排期任务（ST-OPS-02 仍待外部环境）。
