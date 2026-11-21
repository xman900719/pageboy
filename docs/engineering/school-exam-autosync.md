# 校考试卷自动发现、严格匹配与本人排名（ST-EXAM-AUTOSYNC-01）

> 状态（R3 增量）：在 R2 五项卷头与严格匹配基础上，新增 k12100「总分」分析报告册自动下载与全科考试档案补全（`k12100_report_sync.py`、`--mode reports`、迁移 `0017`、`POST /api/school-exams/k12100-sync/report-jobs`）。
> **真实平台与本地环境状态**：已在宿主机通过真实 k12100 会话对「总分 → 报告打印 → 下载PDF」路径与首页 `queryStudentExamDataList` 字段完成只读探测（Phase 0）；「全科校考同步」第 3 步真实联调及 iPadOS 模拟机验收需由 Owner 人工核验放行后方可确认。仓库不入库任何真实私卷、真实学校/学生 PII 或账号凭据。

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

默认目录：`$PAGEBOY_HOME/<development|production>/data/school-exams/inbox/`。API 只读取当前环境的该目录；CLI 的 `--source-dir` 只作为只读来源，文件复制到当前环境 inbox，原文件不删除、不改名。调用 API 需要 `SHUTONG_ADMIN_TOKEN` 或 `--admin-token`。

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

## 13. R3 增量：一键下载 k12100「总分」报告并补全档案

### 13.1 实测交互链路（Phase 0 Probe）

1. **首页列表（`#/jointStudentAnalysisReport/list`）**：接口 `queryStudentExamDataList` 返回 `examData[]`，其中 `examData._id` 为平台考试 ID、`examData.examDate` 为真实考试日期（`YYYY-MM-DD`，不同于 `analysisTime` 发布时间）、`gradeName`/`gradeCode` 为年级、`schoolYearCode` 为学年度、`examName` 为场次名称、`examType` 配合 `examTypeData` 为大类标签、`examSubjectVoList` 首项 `isTotal=1` 为「总分」入口。
2. **报告下载路径**：点击「总分」入口进入 `#/studentAnalysisReport/reportDetails/scrolReport` → 点击左侧「报告打印」（`button.mm_btn:has-text("报告打印")`）→ 进入 `#/studentAnalysisReport/reportDetails/studentReport` → 点击「下载PDF」（`button.download_btn`）触发浏览器 `blob:` PDF 下载。

### 13.2 身份字段来源与日期规则

- **考试日期（`exam_date`）**：从 k12100 首页 `examDate` / `examTime` / 卡片文本按平台实际格式提取。完整日（`YYYY-MM-DD`）精确入库；若平台给出年月（`YYYY-MM`），`SchoolExamReport.exam_date` 保留 `YYYY-MM`、`SchoolExam.exam_date` 与手工建档保持一致锚定当月 1 日。仅当 k12100 完全无日期时阻断自动建档（`awaiting_exam_date`），绝不以抓取当天日期填充。
- **学年度 / 年级 / 考试类型 / 学科**：主来源为下载的分析报告册本地解析；当报告封面 OCR 缺失年级、学年度或类型时，由 k12100 首页元数据补齐；标准类型（`monthly`/`midterm`/`final`/`unified_practice`）写入规范 `exam_type_label` 以与第 2 步卷头匹配器兼容，具体次序（如「统一练习一」）保留在 `title`/`series_title`。
- **试卷录入保留**：第 1、2 步（私有收件箱扫描、五字段卷头匹配、私有附件入档）保持原功能不变；第 3 步不再要求先匹配试卷即可直接运行报告同步，新建/补全后的档案反过来供第 2 步严格匹配。

### 13.3 写入、更新、答案草稿与冲突红线

- **新建 / 更新 / 补全与分科核对隔离**：无匹配且有可解析日期时新建 `SchoolExam`（`source_kind="k12100"`，`confirmed_by_user=False`）；已有唯一未锁定档案时更新总分并补全空身份字段；已人工锁定总分且分值不同返回 `locked_conflict`；非空身份字段冲突返回 `identity_conflict`，均不覆盖原值；多候选返回 `ambiguous`。**确认某一学科总分或确认整份报告均严格分科独立，绝不自动连带锁定同一场次其他未人工核对的学科总分**。
- **全科与各科排名、班级/年级最高分全量同步**：解析并支持折行“年级最高分/得分率”续表与 OCR 水平行，同步写入 `SchoolExam.class_highest`/`grade_highest`、`SchoolExamReport.total_class_highest`/`total_grade_highest`，并通过 `persist_rank_entries` 将各科（`subject_scope=<subject>`）与全科总分（`subject_scope="total"`）班排/年排/最高分写入 `SchoolExamRankSnapshot`（不进入 `guidance.py` 能力画像）。
- **答案与逐题草稿、去重单次持久化**：调用 `generate_item_drafts(..., update_unconfirmed_drafts=True)` 与本地知识点匹配：新增 `ocr_draft` 或更新未人工确认的 `ocr_draft` 得分（保留已有知识点映射）；`confirmed_by_user=True` 或 `manual_entry` 绝对跳过。`register_report_bytes` 按 `sha256`、`external_exam_id` 与规范考试身份将同场不同时间戳/不同来源报告合并为唯一记录，`sync_answer_cards_to_ledger` 按图像哈希去重并清理旧版错位页号附件，绝不重复持久化同场考试或同图答题卡。
- **下载前完整性预检、断点持久与熔断**：启动下载前先执行 `hydrate_incomplete_local_reports` 合并重复记录并从本地已存 PDF 无网补全缺失排名/最高分/答题卡，随后将 `external_exam_ids` 与 `complete_identities` 一并交给浏览器核对；若首页全部场次均已完整同步，直接在首页结束并零下载返回。遇验证码、401/403/429 立即熔断且零写入；每下完 1 份 PDF 原子写回 `--output`，中途退出仍将此前已落盘有效 PDF 解析入库，`GET /api/school-exams/sync-center` 持久展示 `synced_reports` 与 `sync_readiness`。
- **迁移 `0017`–`0019`**：`0017` 为 `school_exam_reports` 新增 `external_exam_id`/`exam_date`；`0018` 新增各科/总分最高分列、排名快照 `highest_score` 及 `uq_school_exam_report_owner_ext_id` 部分唯一索引；`0019` 新增 `canonical_exam_key` 部分唯一索引 `uq_school_exam_report_owner_canonical_key` 与 `uq_school_paper_attachment_exam_sha` 唯一约束，且以 `school_exam_matcher.py` 作为读写共用的身份/去重单一真源、配合 `scripts/audit_dev_school_exams.py` 只读不变量体检与 `build_answer_card_attachments`/`sync_answer_cards_to_ledger` 期望态删余对账防止跨科错配与重扫建重。
