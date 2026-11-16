# ST-EXAM-AUTOSYNC-01 验证记录

> 本记录只陈述实际执行过的检查；真实学校卷源、真实 k12100 连接与真实平台排名保持 `BLOCKED / NOT_VERIFIED`。
> 完整命令、退出码与 Review 证据见任务 Review 包（`ShuTong_ST-EXAM-AutoSync_Review_R2.zip`）。

## 实现范围

- 阶段 A：`scripts/school_exam_pipeline.py`、`school_exam_headers.py`、`school_exam_pipeline.py`；本地 scan / acquire 接口、dry-run、私有 inbox、卷头证据与 SHA 去重。
- 阶段 B：`school_exam_matcher.py` 严格五字段匹配；排名白名单在 PII 清洗前抽取、本人归属校验后独立 append-only 入库；外部总分默认待核对；已锁定总分不覆盖；非唯一匹配不写账。
- 阶段 C：`SchoolExamSyncCenter.vue` 四步工作区替换原同步 Tab；其余四个学校考试 Tab 未重写。
- R2：五项卷头（学年度/年级/类型/学科/日期）、统一练习类型、单一日期字段、无日期不建档、平台 ID/全称消歧、真实版式 OCR 回归、排名归属校验、paper-scoped collection API/CLI 闭环。

## 自动化验证（本地已执行）

| 范围 | 关键断言 | 结果 |
|---|---|---|
| 卷头识别 | 五项必填、统一练习、单一 `exam_date`（完整日/年月）、不识别学校/学期/系列、PII 遮罩、缺失/冲突不猜测、DOCX、真实版式本地 PNG OCR（标题/年级同排、学科下方、右下方小字日期、手写干扰） | PASS |
| 文件安全 | 符号链接、损坏 PDF、权限过宽、路径逃逸、大小/真实类型、SHA 去重、重跑幂等 | PASS |
| CLI | dry-run 零副作用；`--source-dir` 复制不改原件；未配置 acquire 阻断；离线包保留结构化身份/本人排名并可再次归一化 | PASS |
| 严格匹配 | 五项唯一、同月多场统一练习歧义、核心/日期冲突、同日期/±12 天不合并、平台 ID/考试全称消歧、无日期阻断 | PASS |
| 排名 | 本人 class/school 正常、缺失、无效、冲突、他人列表剔除、归属未验证不入档、重复同步幂等、学生端 403、画像为空 | PASS |
| 历史保护 | 锁定总分冲突保留原值；逐题 `ocr_draft` 未确认不进画像；历史行迁移保留 | PASS |
| 迁移 | 0013/0014 往返、`alembic check`、唯一约束、SQLite + PostgreSQL 16 | PASS |
| 管理端 | 四步导航、空状态、扫描、冲突人工确认、入档、排名/总分人工门禁、429 停止、axe 严重违规 0 | PASS（Chromium） |
| Web 单元 | 四步状态、排名缺失人数、核对覆盖、无档案不补 0 | PASS |
| iPad WebKit | 同步中心竖横屏无横向溢出 | PASS |
| OpenAPI/契约 | 生成快照与真实路由一致；JSON Schema 合法/非法样例 | PASS |

## R1 P0 整改状态

| P0 | R2 处置 | 证据 |
|---|---|---|
| 真实卷头模型不符合样例（学校/学期/系列/月份拆分） | 改为五项必填 + 单一 `exam_date`；学校/学期/系列不识别；统一练习独立类型；无日期不建档；真实版式 OCR 回归 | `test_school_exam_matcher.py`，`header-evidence/`（Review 包） |
| 匹配规则依赖旧六字段/日期窗口，同月多场可误合并 | 五字段候选 + 平台 ID/全称消歧；多候选 `AMBIGUOUS`；日期冲突 `CONFLICT`；旧/新规则 diff | `test_school_exam_matcher.py`，`test_school_exam_pipeline.py` |
| 自动采集闭环/本人排名归属未闭环 | paper-scoped collect API + `run --collect-k12100` 唯一匹配闭环；`rank_ownership` 浏览器一致性校验、后端只持久化 verified；历史快照标 unverified | `test_paper_collection_endpoint_*`，`test_cli_collection_helper_*`，`test_unverified_rank_ownership_*` |

## 未验证/阻断

| 项 | 状态 | 原因 |
|---|---|---|
| 真实学校月考/期中/期末卷源自动下载 | BLOCKED / NOT_VERIFIED | 未配置已授权来源适配器；仅实现 fail-closed 接口 |
| 真实 k12100 连接、字段可用性与排名 | BLOCKED / NOT_VERIFIED | 无用户授权的可用账号/测试条件；模拟数据不等于真实联调 |
| PostgreSQL 练习/修订并发 harness | NOT_RUN | 需独立 `scripts/test_practice_concurrency.py` / `test_revision_concurrency.py`；不属于本次新增路径 |
| 真实 iPad 真机人工验收 | PENDING | 自动化 WebKit 仿真不能替代 owner 人工确认 |

## R2 本轮实际计数（2026-11-15）

| 检查 | 实际结果 |
|---|---|
| Python 全量 `pytest tests -q -rs` | **339 passed, 25 skipped** |
| R2 卷头/匹配定向 | **28 passed**（五项、统一练习、单一日期、完整日/年月、真实版式 OCR、同月歧义） |
| 安全定向 | **29 passed** |
| Vitest | **26 passed（4 files）** |
| Chromium E2E | **25 passed, 5 skipped** |
| iPad WebKit E2E | **28 passed, 2 skipped** |
| 同步中心 axe | **violations=0, blocking=0** |
| SQLite 0013/0014 + `alembic check` | **PASS** |
| PostgreSQL 16 0013↔0014 + `alembic check` | **PASS** |
| OpenAPI / JSON Schema / Markdown / Zensical | **PASS** |
| 环境隔离 | **PASS** |
| 真实卷源 / 真实 k12100 / 真实排名 | **BLOCKED / NOT_VERIFIED** |
| 前端 Owner 模拟机人工确认 | **PENDING（未提交）** |

跳过项仍为既有 PostgreSQL 并发 harness（25 项）与设备/视觉门控（Chromium 5、WebKit 2）；未标记为通过。

## 旧版卷头草稿修复（2026-11-15）

- 旧草稿的 `school_name/term/series_title` 不再回传到前端证据与 warnings；API 只暴露五项。
- 「重新执行自动匹配」会重新读取私有原件、重跑五字段识别，而不是仅用旧 `header_fields` 重匹配。
- 日期候选限制在页首 12 行并排除题号行；题干中的历史日期不再被误判为考试日期冲突。
- 开发库 9 份旧草稿已全部重识别；`道法卷.pdf`（期中）恢复为 `2026-2027 / 9 / 期中 / 道德与法治 / 2026-11`。

## 考试日期录入月精度（2026-11-15）

- 管理端所有考试日期输入改为 `type="month"`：新建校考、校考同步中心平台日期。
- API 接受 `YYYY-MM`，内部规范为当月 1 日锚点；历史完整日期保持兼容，不做破坏性回填。
- 管理端列表、详情、候选与卷头证据统一显示 `YYYY-MM`，不显示日。
- Playwright 的 `PYTHONPATH` 改为当前 checkout 绝对路径，避免 E2E 误用已安装的旧 `shutong`。

## 单场校考删除（2026-11-15）

- `DELETE /api/school-exams/{exam_id}?confirm=true`，仅 Owner/admin 可调用；缺少 `confirm` 返回 `SCHOOL_EXAM_DELETE_CONFIRMATION_REQUIRED`。
- 级联删除逐题得分、原卷附件（含私有 blob）与排名快照；关联扫描试卷解除关联并回到待核对。
- 管理端“已录校考台账”每行提供删除 → 确认删除/取消，删除当前选中场次后刷新列表，其他场次保留。

## 私有原件缺失恢复（2026-11-15）

- `rematch` 发现私有 blob 缺失或哈希不符时，会回到当前环境 inbox 按 SHA-256 找回原件并补写 blob，再重新识别。
- 扫描去重时若既有记录 blob 缺失，也会用本次扫描到的原件补写，不改变试卷 SHA。
- 开发库 9 份试卷私有原件已全部恢复；3 份十月试卷的缺失 blob 已补回。
