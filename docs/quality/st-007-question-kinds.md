# ST-007 验证记录：四科题型组合与评分来源可追溯

日期：2026-10-22。分支 `codex/st-003-private-ingestion`（仅本地提交，未推送）。验收口径：IMPLEMENTATION_PLAN ST-007 行（"四科样例和评分来源可追溯"）。全部测试数据为运行时生成的虚构测试数据；PG 验证使用自动创建并清理的一次性容器。

## 实现（最小范围）

- **kind 判分矩阵**：`single_choice`（strip 全等）/ `short_answer`（**归一化判分** `norm(s)=" ".join(s.split()).casefold()`，无既有依赖，已核实零测试/前端引用旧行为）/ `subjective`（提交即 `ungraded_subjective`、earned None）。`QuestionIn` 扩充 kind Literal、`group_context`（≤20000）、`media_attachment_id`；subjective 须空选项。
- **题组/阅读**：`group_context` 按版本自包含；修订新版本可改文段。
- **听力音频**：`MEDIA_TYPES` += audio/mpeg、audio/mp4（魔数校验：ID3/0xFFEx 帧头、ftyp@4）；`parse_attachment` 音频分支直通 `needs_manual_input`（不引入转写）；confirm-import 载荷可带 `media_attachment_id`；练习响应含 `media_attachment_id`，客户端经**既有** owner 鉴权下载路由取音频——零新增字节端点。
- **主观自评**：新表 `self_assessments`（attempt 唯一、无更新路径、`scoring_origin="self_assessment"`）；`GET /api/practice/attempts/{id}/reference`（作答先行门）；`POST .../self-assessment`（越界 422、重复 409、并发竞争 IntegrityError→回滚重查→409/如实抛出）；**自评不进客观证据**（get_evidence 不读该表）。
- **溯源审计**：`GET /api/practice/attempts?subject=`（created_at desc, id desc；每条含 kind/origin/self_assessment 关联）。
- **媒体引用校验**：三个创建路径（add_question / confirm_import / revise_question）一致校验存在/同源/owner → 422 `MEDIA_ATTACHMENT_INVALID`（revise 路径为 Gate 整改补齐）。
- 迁移 `0005`：question_versions 两新列（条件式、**无数据库级 FK**）+ self_assessments（含 `ix_self_assessments_learner_id` 与 `uq_self_assessment_attempt`）；OpenAPI 重新生成校验（+146/-0 纯增量）。

## 实际命令与结果

### Red（实现前，2026-10-22）

- 新 4 测试文件 13 项：**12 红**（422 未知 kind subjective、KeyError group_context、音频 415 未白名单、404/405 缺路由、缺表缺列）+ **1 绿**（物理图表样例对既有判分的回归护栏）。全套件零附带损伤。

### Green（实现后，均由 orchestrator 复跑）

- SQLite：`cd services/api && python -m pytest -q` → **110 passed, 25 skipped, 0 failed**（96 既有 + 13 X1 + 1 Gate 整改回归）。
- `PATH="$PWD/.venv/bin:$PATH" make verify` → 全 PASS；`.venv/bin/zensical build --strict` 无问题；`git diff --check` 干净。
- SQLite alembic 往返（新库 0001→head→check 与 遗留 降级→升级→check 两路径）全部干净。
- **docker PostgreSQL 16.15**（一次性容器，均用后清理）：
  - 0005 迁移腿（修复后）：全新库 `upgrade 0001` → `upgrade head` → `check` → `downgrade 0004` → `upgrade head` → `check` 全净；关键表齐备。
  - 跨任务回归：`python scripts/test_practice_concurrency.py` 全量 → **EXIT 0**（迁移腿 OK + ST-004 的 19 项真并发全绿——ST-005/006/007 变更未破坏练习/曝光/幂等语义）。
- 四科样例全链（测试内）：数学（公式文本题干+短答归一化 2/0 分双例+主观解答自评）、语文（阅读题组 group_context 共享×2+作文自评）、英语（合成 mp3 上传→parse needs_manual_input→confirm-import→发布→练习响应含 media_attachment_id→下载路由取回**逐字节相等**；阅读题组；短答大小写归一）、物理（图表文本题干+选择回归）；主观链（参考答案作答后可取、自评 201/重评 409/越界 422/非主观 409）、溯源列表（11 键精确形状、owner 隔离、origin 分型正确）、自评不入 profile。

## 关键缺陷捕获与修复（如实记录，2026-10-22）

- **CRITICAL（docker PG 迁移腿捕获，SQLite 全绿掩蔽）**：初版 `QuestionVersion.media_attachment_id` 带内联 `ForeignKey("source_attachments.id")`——`source_attachments` 属 0002 表，全新 PostgreSQL 库 `alembic upgrade 0001` 建表即失败（`relation "source_attachments" does not exist`）；SQLite 建表时不校验悬空 REFERENCES，故全部本地测试与迁移循环都绿。ST-004 的 `question_id` 内联 FK 之所以成立，是因为其目标表同属 0001 批次。修复：模型改普通 String(36) 可空列（注释说明缘由）、0005 改普通条件 add/drop（去 batch FK）、迁移测试 FK 断言替换、设计 §1/§4 修订；引用完整性由三个创建路径的应用层校验承担。修复后全新 PG 0001→head 全净。
- **流程教训**：models.py 变更必须重跑 docker PG 迁移腿——本次并发脚本的迁移腿正是唯一能捕获该缺陷的护栏。
- Oracle 门禁 APPROVE-WITH-CHANGES：MINOR#1（自评端点并发 IntegrityError 处理）已整改（回滚重查模式与 submit_attempt 一致）；MINOR#2（设计措辞）已同步；MINOR#4（归一化规则与无 FK 不变量写入 data-model.md）已落实；MINOR#3（三处校验重复，保留局部性不改）、MINOR#5（形状信息项）记录不改。

## 限制与未验证

- 短答归一化对"值内含意空白/单位"敏感（data-model.md 已声明边界）；富文本公式/图表渲染属 ST-008 前端范畴，API 仅文本承载；音频无转写/时长校验。
- 自评不进画像/复测（进入须另立 ADR）；同卷同题号防重不适用于练习题（由曝光幂等约束）。
- 远端 CI 未运行；前端未改动、未构建（ST-008 范畴）。

下一项任务：**ST-008**（精简学习首页、复练、阶段诊断、缺证据解释——真实用户旅程与 Playwright）。
