# ST-006 验证记录：学校私卷上传与逐题人工核对

日期：2026-10-21。分支 `codex/st-003-private-ingestion`（仅本地提交，未推送）。验收 ID：AC-EVI-01、AC-EVI-02、AC-SEC-01。全部测试数据为运行时生成的虚构测试数据；PG 验证使用自动创建并清理的一次性容器。

## 实现（最小范围）

- **迁移 `0004`**（新表，无 0001 冲突）：`school_exam_items`（逐题得分；`(school_exam_id, question_label)` 唯一约束；`scoring_origin ∈ {manual_entry, ocr_draft}` 原始来源保留；`confirmed_by_user`/`confirmed_at` 人工门禁）与 `school_paper_attachments`（复用 ST-003 私有存储：魔数/页数/像素/10MiB、0600 独占写、sha256；`storage_key` unique）。
- **端点**（owner 鉴权）：`POST /api/school-exams/{id}/items`（批量录入 ≤100；manual_entry 建即确认，ocr_draft 建即未确认；批内/跨批题号冲突 409 `SCHOOL_ITEM_LABEL_CONFLICT`，回滚无部分写入）、`POST .../items/{item_id}/confirm`（仅 ocr_draft；必须 `confirmed_by_human=true`；可修正识别分；确认后不可变：同分重复确认 409 ALREADY_CONFIRMED、异分 409 IMMUTABLE）、`GET /api/school-exams/{id}`（详情+items+附件元数据，存储键绝不序列化）、`POST .../paper`（镜像 ST-003 上传梯：415 白名单→413 流式 10MiB→422 空/哈希不匹配→魔数校验→独占落盘，存储失败回滚+清理）。
- **证据装配**：`get_evidence` 并入已确认校卷 item（合成键 `school-item:{id}`，独立=True、首曝=True，与练习评测互为不同观测）；总分行永不进证据（INV-05）；ST-005 复测装配不含校卷条目。
- **隔离边界（AC-SEC-01）**：不存在任何读取校卷附件字节的端点；校卷附件不与 source_documents 关联，内容台账/题目草稿/发布/练习均无法引用；存储键不出现在任何响应或 OpenAPI。
- API 变更已重新生成并校验 `contracts/openapi.yaml`（+242/-0，仅 4 个 school-exams 子路径与 3 个 schema）。

## 实际命令与结果

### Red（实现前，2026-10-21）

- 新 3 测试文件 16 项：**15 红**（路由 404/缺表——纯功能缺失）+ **1 绿**（总分回归护栏：totals-only → `knowledge_evidence_created: False`、profile `[]`）。全套件 15 failed / 80 passed / 25 skipped，零附带损伤。

### Green（实现后，均由 orchestrator 复跑）

- `cd services/api && python -m pytest -q` → **96 passed, 25 skipped, 0 failed**（含 Gate 整改新增的 413 流式上限与 UPLOAD_HASH_MISMATCH 独立覆盖）。
- `PATH="$PWD/.venv/bin:$PATH" make verify` → contracts/docs/openapi 全 PASS；`.venv/bin/zensical build --strict` 无问题。
- **SQLite 迁移往返**（test_school_migration.py）：0001→head→check→种子（含唯一约束探针 IntegrityError）→downgrade 0003（两表删、source_documents 与 school_exams 基础行保留）→head→check→探针仍生效。
- **docker PostgreSQL 16.15 一次性迁移腿**（容器用后清理）：`upgrade head`→`alembic check` 干净→种子→`downgrade 0003`（0004 两表删除、基础表行保留）→`upgrade head`→`check` 干净；独立新库上重复题号被 `uq_school_exam_item_label` 实际拒绝（`Key (school_exam_id, question_label) already exists`）。注：首次探针误设在往返后的空表上（无冲突可拦），已在新库重测为 True——如实记录。
- 关键行为断言：仅总分 → 无证据；manual_entry 建即确认并产生证据；ocr_draft 三条（3/4、1/4）不产生证据 → 人工确认（第二条修正为 2/4）后 profile `math.geometry` sample 2、rate 0.625；确认不可变 409 两码；批内/跨批题号冲突原子拒绝；合成 PNG 上传 201 响应恰 6 键无存储键、落盘 0600、私有目录文件数 +1；415/422/413/哈希不匹配全梯；内容台账/题目草稿/练习均不可见校卷附件；无任何字节路由（探测 404/405）；校卷+练习证据合并 sample 4；校卷条目不进复测装配。

## Oracle 门禁

APPROVE-WITH-CHANGES：三项验收判定 SOUND/无缺陷；MINOR#1（学校端点独有的 413/哈希不匹配路径缺独立测试）已整改；MINOR#2（防御直改库越界行的不可达分支）保留并加注释；MINOR#3（不可变 409 优先于 422 边界检查）记录不改。整改后全套件 96 passed。

## 限制与未验证

- OCR 分数表解析未实现（"OCR 可选"——draft 条目来源不限于真 OCR，工作流语义相同）；不存在校卷附件浏览/下载端点（当前无此需求）；附件追加式无删除。
- 首次上传哈希不匹配与超限仅在 SQLite 测试环境验证（隔离库），无生产环境。
- 远端 CI 未运行；前端未改动、未构建。
- 确认语义为"人工录入即人工确认"，不代表教师复核或法律效力。

下一项任务：**ST-007**（四科题型组合）。
