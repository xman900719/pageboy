# 校考试卷自动发现、严格匹配与本人排名（ST-EXAM-AUTOSYNC-01）

> 状态（R2 修正）：五项卷头模型（含单一 `exam_date`）、五字段严格匹配、真实版式 OCR 回归、本人排名归属校验、paper-scoped 采集闭环已实现并有自动化测试。
> **真实学校卷源与真实 k12100 平台联调仍为 `BLOCKED / NOT_VERIFIED`**：仓库没有已审核的学校月考/期中/期末卷源及授权方式；本机也没有可使用的真实账号验收条件。本文不会把模拟数据测试表述为真实平台验证。

## 1. 目标与边界

目标流程：

**本地自动发现/取得试卷 → 卷头识别 → 精确匹配考试 → 获取本人信息 → 人工核对 → 正式归档 → 错误分析。**

本实现只做增量：

- 保留既有手工建档、原卷上传、逐题草稿人工确认与错误分析。
- 保留既有五学校考试 Tab，只重构「全科校考同步」内部交互为四步。
- 保留 `ocr_draft` + `confirmed_by_user=False` 门禁；自动采集的总分默认待人工核对。
- 不把学校私卷、答题卡、排名写入公开题库或学生练习流。
- 不采集/不持久化其他学生数据。

## 2. 组成

| 层 | 位置 | 职责 |
|---|---|---|
| CLI | `scripts/school_exam_pipeline.py` | `scan` / `acquire` / `run`，`--dry-run`、`--env`、`--source-dir` |
| 私有服务 | `services/api/shutong/school_exam_pipeline.py` | 收件箱、验证、归档、扫描审计、匹配编排、附件复用、个人排名 |
| 卷头识别 | `services/api/shutong/school_exam_headers.py` | 本地文字层/OCR、字段级证据、置信度、PII 遮罩 |
| 严格匹配 | `services/api/shutong/school_exam_matcher.py` | 五类匹配结果与字段差异（纯函数，无 I/O） |
| 数据 | `alembic/versions/0013_school_exam_autosync.py`、`0014_exam_header_r2.py` | 考试身份元数据、试卷索引、扫描审计、本人排名快照、类型原标签与排名归属字段 |
| API | `services/api/shutong/main.py` | 仅管理端可访问的扫描/匹配/入档/排名接口 |
| 管理端 | `apps/web/src/components/admin/SchoolExamSyncCenter.vue` | 四步工作区；桌面与 iPad 响应式 |
| 采集安全 | `scripts/k12100_browser.mjs`、`k12100_backfill.py` | 低频串行、会话复用、风控立即熔断 |

## 3. CLI 工作流

```bash
# 只读预演：不创建 inbox、不复制文件、不写数据库、不发 API
uv run python scripts/school_exam_pipeline.py scan \
  --env development --source-dir ~/已授权试卷 --dry-run --json

# 将指定目录的合法试卷复制进当前环境 0700 inbox，扫描并登记为待核对
uv run python scripts/school_exam_pipeline.py scan \
  --env development --source-dir ~/已授权试卷

# 扫描 + 唯一精确匹配 + 自动私有入档；不自动确认总分
uv run python scripts/school_exam_pipeline.py run --env development

# 本地闭环：唯一已匹配试卷 → paper-scoped 单场采集 → 轮询到完成/失败
uv run python scripts/school_exam_pipeline.py run --env development --collect-k12100

# 真实授权来源适配器；当前未配置时明确返回 SOURCE_NOT_CONFIGURED
uv run python scripts/school_exam_pipeline.py acquire --env development
```

默认目录：`$PAGEBOY_HOME/<development|production>/school-exams/inbox/`。API 只读取当前环境的该目录；CLI 的 `--source-dir` 只作为只读来源，文件复制到当前环境 inbox，原文件不删除、不改名。调用 API 需要 `SHUTONG_ADMIN_TOKEN` 或 `--admin-token`。

`--collect-k12100` 只允许**恰好一份**唯一匹配试卷；零份或多份均 fail-closed，不猜测采集目标。采集任务仍默认 `confirm_total_scores=False`，真实账号/运行环境未配置时由 API 返回阻断，不会伪报完成。

paper-scoped 采集不再把**本地手工档案标题**当作平台搜索关键词（本地标题不等于平台场次全称）；改为采集最近单场后走五字段严格匹配。浏览器返回空场次/空科目时分别报 `K12100_NO_EXAMS` / `K12100_NO_SUBJECTS`，不再误报 `K12100_INVALID_BUNDLE`；只有畸形 JSON 才属于 invalid bundle。

## 4. 文件与路径安全

- 仅接受 PDF / DOCX / PNG / JPG / JPEG；扩展名只用于选择 MIME，真实类型由 `private_files.validate_file` 的魔数/结构/页数/像素校验决定。
- 单文件不超过 35 MiB；扫描最多 200 个文件、目录深度 3。
- 拒绝符号链接文件和目录；所有命中路径必须位于解析后的来源根目录。
- inbox 必须为 `0700`，登记文件为 `0600`；权限过宽 fail-closed，不静默修改既有目录权限。
- SHA-256 去重；同名不同内容按哈希区分；原始 blob 只写入当前环境私有存储。
- `--dry-run` 不写数据库、文件、台账或外部平台状态。
- 所有自动入档只把原件作为 `SchoolPaperAttachment` 私有附件，不读取附件字节的公开端点仍然不存在。

## 5. R2 卷头识别（只识别五项，含单一 exam_date）

本地优先：PDF 前两页文字层、DOCX 文本；无文字层时对前两页完整页图做本地 tesseract OCR，覆盖右下方小字区域。**不调用外部 AI 识别卷头**。

只识别五项：

| 字段 | 规范值示例 |
|---|---|
| 学年度 | `2026-2027` |
| 年级 | `9`（同时兼容“九年级/初三”等原卷写法） |
| 考试类型 | `monthly` / `midterm` / `final` / `unified_practice` / `other`（保留明确原标签） |
| 学科 | `ethics`（道德与法治）、`math` 等 |
| 考试日期 | 单一 `exam_date`：完整日期 `2026-10-12`，或原卷只写年月 `2026-10` |

**不再识别学校、学期、考试系列**；它们不出现在识别结果、API 卷头、字段证据或 UI 中。`统一练习` 保留为 `unified_practice`，绝不规范化为月考/期中。

`exam_date` 是单一字段，不拆分 `exam_month`/`date_precision`。完整日期按原样保存；只有 `2026.10` 时保存 `2026-10`。**不把缺失日补为 01 日、当前日期、发榜日期或其他推测值**；`school_exams.exam_date` 的既有非空日精度没有被伪造写入，平台无完整日期时不自动建档。

日期缺失、多个不同日期、年级/类型冲突或五项任一缺失时 `complete=false` 并进入人工核对。

OCR 保存完整脱敏卷头文本、文本 SHA-256、字段级值/状态/证据与总体置信度。姓名/学号/考号等在保存前遮罩；真实扫描件仍只存私有附件。

## 6. R2 五字段严格匹配

候选筛选仅要求五项核心字段：

`academic_year + grade + exam_type + exam_date + subject`

学校、学期、考试系列不参与匹配，也不出现在卷头。日期规则：

- 两边都是完整日期：必须同日；
- 任一方只有年月：按年月比较；
- 不同月/不同日 => `CONFLICT`，不静默修正；
- 同日期、同月、±12 天邻近关系都不单独构成确认依据。

五个核心字段全部一致只形成候选资格；多个候选时优先用平台考试 ID，再用考试全称消歧；仍不能唯一确定时返回 `AMBIGUOUS`。

平台日期与卷头日期的冲突作为核心冲突处理，**不静默修正日期**。平台完全没有可验证完整日期的场次不会创建 `SchoolExam`；返回 `match_state="AWAITING_EXAM_DATE"` 和 `score_status="match_blocked"`。

非 `EXACT_MATCH` 的 k12100 科目结果以 `score_status="match_blocked"` 返回，不写总分、不写草稿、不写附件。`EXACT_MATCH` 才可继续。

## 7. 排名保留与隐私

原始 XHR 的排名字段仍属于 PII 清洗范围。新流程在递归清洗**之前**，只从当前本人科目单值字段抽取以下白名单：

- 范围：`classRank` / `gradeRank` / `schoolRank` / `regionRank` / `examRank`（平台无更细语义时归入学校范围并保留原字段名）
- 人数：对应范围总人数、`examNum` / `actualExamNum`
- 平台百分位：`*rankRate`

R2 还要求**归属校验**：浏览器只从当前已认证科目响应中提取学生标识，且所有已见标识必须一致；没有标识或多个冲突标识时输出 `rank_ownership="unverified"/"conflict"`。后端只持久化 `verified` 的排名，未验证项附 `RANK_OWNERSHIP_UNVERIFIED` 问题且不入档；`ownership_status`/`ownership_basis` 随快照保存，人工确认排名也不得绕过归属校验。

然后在 `school_exam_rank_snapshots` 中 append-only 保存：排名值、人数、百分位、来源字段、来源、采集时间、本人归属校验、人工核对状态。相同内容哈希幂等；变化值保留历史。缺失值存 `null` 并返回缺失范围，不补 0。排名不进入 `guidance.py`、学生端画像、错误分析草稿或成绩预测。

导出/离线包只保留结构化 `own_ranks` 与结构化考试身份 `identity`；不保留 `schoolRank`/`schoolName` 等原始敏感键或学生列表。`students` 等他人明细集合在导出前删除。身份字段在清洗前抽取，经 round-trip 测试可再次参与严格匹配。

## 8. 总分与逐题门禁

- 新的 `import-bundle` / 采集任务默认 `confirm_total_scores=False`；平台总分只作为待核对候选。
- 已人工锁定 `school_exams.confirmed_by_user=True` 时，任何不同总分只返回 `locked_conflict`，保留原值。
- 逐题外部数据一律 `scoring_origin="ocr_draft"`、`confirmed_by_user=False`；人工确认后才进入能力证据。
- 自动导入试卷只填 `school_exams` 的空身份字段，绝不覆盖既有总分、已确认逐题或排名历史。

## 9. 平台低频与熔断

仅使用当前已授权本人账号；默认单场、单账号、单会话串行、可见浏览器、复用登录会话。出现验证码、滑块、401、403、429、账号异常或平台规则不允许时立即停止；禁止代理轮换、指纹伪装、验证绕过、隐藏自动化或未授权接口。真实平台无授权时降级为人工或离线包导入。

## 10. 数据库迁移与回退

迁移 `0013` 建立试卷索引/排名快照；R2 迁移 `0014`：

- `school_exams.exam_type_label`：保存真实非标准类型原标签，避免 `other` 折叠误配。
- `school_exam_rank_snapshots.ownership_status / ownership_basis`：保存本人归属校验状态与依据；历史快照无归属证据时默认 `unverified`，不伪造 `verified`。
- 既有成绩行、已确认逐题、知识点发布版本不受影响；`SchoolExam.exam_date` 仍保持日精度，卷头 `exam_date` 可以只到年月，但不会写入伪造日。

升级后跑 `alembic check`。隔离 SQLite 与 PostgreSQL 16 已验证 0013/0014 往返、唯一约束和历史行保留。**生产降级不自动执行**：如已有排名/试卷索引，应先备份并人工确认。

## 11. 真实数据依赖（阻断）

- R2 已增加真实版式脱敏回归（标题/年级同排、学科下方、右下方小字日期、手写批注干扰）；这不是对 Owner 真实私卷的验收。
- 未配置真实、获授权的学校月考/期中/期末卷源，因此 `acquire` 返回 `SOURCE_NOT_CONFIGURED`；自动远程下载 `NOT_VERIFIED`。
- 未提供可用 k12100 账号/授权环境，真实连接、真实字段可用性与真实排名 `NOT_VERIFIED`。
- 本地 OCR、模拟采集包解析、严格匹配、排名清洗、迁移和 UI 自动化均已执行；模拟测试不等于真实平台联调。

## 12. 验证

```bash
cd services/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests -q
cd apps/web && npm run test:unit && npm run build
cd apps/web && npm run test:e2e
cd apps/web && npm run test:e2e:ipad
python scripts/check_openapi.py
python scripts/validate_contracts.py
scripts/check_env_isolation.sh
```

详细需求映射、命令退出码与限制见 Review 包中的 `tests/TEST_MATRIX.md`、`tests/TEST_COMMANDS.md` 与 `REAL_WORLD_VALIDATION.md`。
