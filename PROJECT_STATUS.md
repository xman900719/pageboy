# 书童 Codex 交接时点的真实状态

## 提供的可运行组件

- FastAPI 私有 API（owner Bearer Token）、SQLite 本地开发适配/PostgreSQL 配置、Alembic 基础迁移。
- 来源台账、私有 PDF/图片原件与哈希、本地 PDF 文本/图片 OCR 草稿、人工确认、草稿/审核/发布选择题与修订新版本、曝光记录、自动判分、简单幂等答题、总分学校卷记录、Goal 版本、启发式画像和训练计划。
- React Web/PWA 交互骨架与三视图学习 UI（首页/练习复练/阶段诊断，Playwright J1–J4 用户旅程通过）；PWA **只缓存静态壳，不离线缓存学生数据/API**。
- OpenAPI 快照、JSON Schema 验证及反例、Markdown 图片/链接校验、测试、已验证的 GitHub CI、备份模板。

## 尚未实现且不得宣称完成

复杂试卷/公式/图表自动结构化、混合版式 PDF 部分 OCR、真实资料来源法务评审、真实试卷 OCR 准确率评估、正式目标蓝图、可比独立验证与成绩效果评价、多用户访问身份管理。练习会话轮换、曝光原子化与作答幂等（ST-004）、数学纵向闭环与独立复测对比（ST-005）、学校私卷逐题人工核对与附件隔离（ST-006）、四科题型与评分来源可追溯（ST-007）、学习首页/复练/阶段诊断/缺证据解释用户旅程（ST-008）、iPad WebKit 仿真通道（ST-010）、人工审核台 UI（ST-011）、PWA 图标与选配记住令牌（ST-012）、题干公式渲染（ST-013）、扫描 PDF OCR 摄取（ST-014）、题库体检（ST-015）、生产栈与真机 iPad 全链核对（ST-016）、标签化部署/回滚（ST-017）、诊断未见题会话续答（ST-018）以及 R2 异地备份恢复与告警（AC-OPS-01/02）均已实现并通过验证（均见下文），但小规模验证不代表吞吐达标或效果推断；真实中文试卷扫描件的 OCR 准确率仍待首次真卷导入时评估。

## 当前环境验证记录（2026-10-18）

ST-001 已完成本地基线与远端 CI 验证，AC-DOC-01/02/03 均通过。完整命令、初始失败及修复证据见 [ST-001 验证记录](docs/quality/st-001-baseline.md)。此结论仅覆盖 ST-001，完整 MVP 与运行灾备仍未完成。

- Python API/业务测试：8 passed；文档检查器测试：2 passed。
- Schema 正反例、22 篇 Markdown 链接/图片、API/OpenAPI 快照一致性：通过。
- 隔离临时 SQLite 数据库 Alembic 初始迁移：通过，`0001 (head)`。
- Web：初始构建因缺少 Vite 类型声明失败；修复后 `npm ci` 与 `npm run build` 通过。
- Zensical：初始严格构建因站点外 Markdown 链接失败；修复后严格构建通过。
- GitHub Actions：仅修改 `AGENTS.md` 的 `4a5dd6f` 触发 push CI，两个作业全部通过；[实际运行](https://github.com/xman900719/pageboy/actions/runs/39117777469)。基线提交和后续文档提交的 CI 也通过。
- PostgreSQL 16.15：ST-002 修订接口的隔离真实并发验证通过（6 轮、每轮 8 请求/8 连接）；完整应用容器联调、VPS/Tailscale 部署、备份还原仍未验证。
- 本地 Python 为 3.14.4，远端 Python 3.12.15 已验证。测试有一条 Starlette/httpx 弃用警告；Actions 有 Node 20 运行时弃用提示，均未导致失败。

## 优先风险

1. （已关闭，ST-004）曝光并发的未见争用已由数据库级原子认定与真并发验证解决。
2. 私人身份验证是单用户 token 方案，只适合隔离私网环境，不能公网裸奔。
3. 备份脚本只处理 DB，不覆盖已实现的私有原件；真实数据落库前必须完成联合备份和隔离恢复。
4. `personal_use_reviewed` 仅表示手动标注，不是实际版权法律结论。
5. （已关闭，ST-004）曝光选择的原子化与并发验证已完成。


## ST-002 本地验证（2026-10-18）

已实现已发布题的修订草稿接口，新练习使用最新已发布版；旧版、曝光、作答和评分保持不变，同一题换版不恢复未见资格。本地新增 12 项正反例测试通过；另有 6 轮隔离 PostgreSQL 真实并发测试通过，旧历史保持不变。普通门禁为 API/业务 20 passed、6 项 PostgreSQL 集成测试明确 skipped；文档检查器 2 passed，Schema、23 篇 Markdown、OpenAPI、Zensical 严格构建均通过。本轮仅本地提交，ST-002 远端 CI 未运行。验收及兼容/回滚边界见 [ST-002 验证记录](docs/quality/st-002-question-revisions.md)。


## ST-003 本地验证（2026-10-18）

来源台账、原件私有存储、哈希校验、本地 PDF 文本/PNG/JPEG OCR 草稿、人工确认与发布门禁已实现。测试只使用运行时生成的虚构测试数据。SQLite 升降级/再升级及 PostgreSQL 16.15 升级均保留原来源；不代表恢复演练。完整测试与限制见 [ST-003 验证记录](docs/quality/st-003-private-ingestion.md)。本轮仅本地提交，远端 CI、生产部署与联合备份未验证。下一项 ST-004。

## ST-004 本地验证（2026-10-19）

练习会话（最小无状态）、确定性题目轮换、曝光原子化与作答幂等已实现：training 不再总返回排序首题；`exposures.question_id` + 部分唯一索引保证每学习者每逻辑题至多一次未见首曝（跨版本）；`answer_attempts` 每曝光至多一条有效作答，同键/同曝光并发由提交点唯一约束裁决，零未处理 500。隔离 PostgreSQL 16.15 完成迁移往返（含回填断言）与 19 项真并发测试全绿（8 请求/8 独立连接/轮，natural+colliding 受控竞争窗）；普通门禁 API 67 passed、25 skipped（可选 PG 并发项），Schema/文档/OpenAPI/zensical --strict 均通过。实现前 red 反例证实竞争真实存在（未处理 500、幂等重试被误答 409）。本轮仅本地提交，远端 CI、前端构建与吞吐压测未验证。详见 [ST-004 验证记录](docs/quality/st-004-practice-session.md)。下一项 ST-005。

## ST-005 本地验证（2026-10-21）

数学纵向闭环（目标→证据→画像→差距→计划→独立复测）已实现：`compare_validation` 纯函数 + `GET /api/guidance/validation`，基线=每知识点前 3 条独立未见评测证据、其后为复测；不足即 `cannot_compare`/`CANNOT_COMPARE`，相等不宣称 improved，恒 `score_prediction: None` + 免责声明（AC-VAL-02）；guidance 纯度由 AST 白名单+符号扫描+子进程三测试静态锁定（AC-GAP-02）；规则调整回放测试证明历史 AnswerAttempt 逐值不可变（AC-GAP-03）；空/不足证据一律 INSUFFICIENT_EVIDENCE/CANNOT_COMPARE 绝无 0 分（AC-GAP-01）。API 79 passed、25 skipped、0 failed；OpenAPI 重新生成并校验（仅新增 validation 路径）；make verify/zensical --strict 通过。过程缺陷（V1 测试 monkeypatch.undo 共享实例陷阱）已如实记录并最小修复。远端 CI、前端构建未验证；小样本对比不代表效果推断。详见 [ST-005 验证记录](docs/quality/st-005-math-loop.md)。下一项 ST-006。

## ST-006 本地验证（2026-10-21）

学校私卷逐题人工核对与附件隔离已实现：迁移 `0004` 新增 `school_exam_items`（题号唯一约束、`scoring_origin` 原始来源保留、`confirmed_by_user` 人工门禁——ocr_draft 未经人工确认绝不产生证据，AC-EVI-02；总分永不折算考点证据，AC-EVI-01）与 `school_paper_attachments`（复用 ST-003 私有存储；无任何字节读取路由、存储键不进响应、与内容台账/题目草稿/发布/练习结构性隔离，AC-SEC-01）。已确认 item 以合成键并入 profile 证据且不进复测装配。API 96 passed、25 skipped、0 failed（red 先行 15 项）；SQLite 迁移往返 + docker PostgreSQL 16.15 一次性迁移腿（含唯一约束实际拦截证据）；OpenAPI 重新生成校验（+242/-0）；oracle 门禁 APPROVE-WITH-CHANGES，MINOR#1 已整改。OCR 分数表解析未实现（"OCR 可选"，工作流语义相同）。远端 CI、前端构建未验证。详见 [ST-006 验证记录](docs/quality/st-006-school-papers.md)。下一项 ST-007。

## ST-007 本地验证（2026-10-22）

四科题型组合与评分来源可追溯已实现：kind 判分矩阵（single_choice 精确 / short_answer 归一化 `casefold+空白折叠` / subjective 提交不判分）；题组/阅读 `group_context`（版本自包含）；听力题 `media_attachment_id` 复用内容附件管线（音频魔数校验、无新增字节端点）；主观自评独立表 `self_assessments`（作答不可变、attempt 唯一、不进客观证据）；`GET /api/practice/attempts` 评分来源审计列表。SQLite 110 passed / 25 skipped / 0 failed；docker PG 0005 迁移腿全净 + ST-004 并发脚本全量回归 EXIT 0。**关键缺陷修复**：初版 media 列内联 FK 引用 0002 表使全新 PG 库 `upgrade 0001` 失败（SQLite 容忍悬空 REFERENCES 掩蔽、docker PG 捕获）——改为无 FK + 三创建路径应用层校验，教训：models 变更必须重跑 PG 迁移腿。oracle 门禁 APPROVE-WITH-CHANGES（MINOR#1 自评并发处理已整改）。富文本渲染属 ST-008；远端 CI、前端构建未验证。详见 [ST-007 验证记录](docs/quality/st-007-question-kinds.md)。下一项 ST-008。

## ST-008 本地验证（2026-10-22）

学习首页/复练/阶段诊断/缺证据解释已实现并通过 Playwright 用户旅程（J1–J4 全绿，chromium，10.9s）：三视图 UI（designer 交付）、题型渲染（题组区块/听力音频授权加载/主观自评链终态）、诚实文案红线零违规（grep 实证）、令牌仅内存、PWA 仍只缓存静态壳。纯前端任务零后端改动（后端 110 项护栏不变）。双 webServer harness（uvicorn:18765 临时 SQLite + vite preview:4173 同源代理；宿主 8000 被无关服务占用，不停外部服务改用 18765）；种子全部虚构测试数据经管理 API 现场注入。oracle 门禁 APPROVE（无 MATERIAL）。远端 CI 未运行；单浏览器无性能断言。详见 [ST-008 验证记录](docs/quality/st-008-user-journeys.md)。下一项 ST-009。

## ST-009 收口验证（2026-10-22；远端 CI 于 2026-10-23 补验通过，见该记录）

Docs as Code/可访问性/契约与 CI 全面核对完成：README 功能清单同步、overview 审计确认、契约三次增量再生成全部一致；CI 新增 `pg-migration`（全新 PG 0001→head→downgrade 0004→head→check——ST-007 缺陷类的永久护栏，SQLite 无法拦截）与 `web-e2e` 两个作业（命令经本地等价环境逐字验证；**远端未运行不标通过**）；新增 axe-core 三视图 WCAG A/AA 扫描并修复 31 个 color-contrast serious 节点（designer 会话，仅 style.css 8 行颜色值）；ST-002 修订并发 docker 回归 6/6、ST-004 练习并发回归 19/19（跨全部五次迁移）。终验：Playwright 7/7、后端 110 passed/25 skipped、make verify、zensical --strict 全绿。**开发计划 ST-001~ST-009 全部本地验收完成**；剩余 ST-OPS-01/02 受外部环境与授权门禁约束（AC-OPS-01/02 仍未演练，真实长期数据落库前必须完成）。详见 [ST-009 验证记录](docs/quality/st-009-closure.md)。

## ST-OPS-01 本地基础工作（2026-10-22，边界如实）

按备份策略权威文档要求，`infra/backup.sh` 已扩展为 **DB+附件联合备份模板**（附件 tar.gz、双文件 SHA256SUMS、含 migration_revision 的 manifest；`BACKUP_OUTPUT_DIR` 进入本地演练模式跳过 restic——restic 本地未装）；新增隔离恢复模板 `infra/restore.sh`（SHA 校验、拒绝非 pageboy 库名/非空附件目录、pg_restore、迁移版本比对告警）与本地端到端演练 `scripts/smoke_joint_restore.py`（compose 全新双实例：种子→联合备份→摧毁→恢复→冒烟，行数/迁移版本/附件 sha 字节一致、练习可服务；orchestrator 亲跑 + lane 两轮共三次通过，清理幂等）。**这不构成 AC-OPS-01**：异地/另一故障域备份、restic 生产路径与保留策略、密钥隔离、真实 RPO/RTO 均未验证，策略状态保持 PROPOSED/UNVERIFIED。剩余 ST-OPS-01 异地部分与 ST-OPS-02 需 VPS/备份仓库/运行环境与明确授权。

## ST-OPS-01 异地闭环达成（2026-10-25）

**AC-OPS-01 与 AC-OPS-02 均达成**：R2 异地备份→隔离恢复→端到端冒烟全绿（33s 备份/7s 拉回/1s 恢复/3s 冒烟）；healthchecks.io dead-man's switch 告警接通（ping 200 实测、4h+1h=5h 静默告警）；用户级 crontab 每 4 小时调度已生效。

## ST-013~ST-018 验证与 v1.6.1 生产收口（2026-10-29 ~ 11-01）

- **ST-013~ST-015 / ST-017**：题干公式渲染（ST-013，KaTeX `$…$`/`$$…$$`，纯函数切分+文本转义，单测 9/9、chromium 13p/3s、iPad/WebKit 16p，[记录](docs/quality/st-013-formula-rendering.md)）、扫描 PDF OCR 摄取（ST-014，无文本层 PDF pdftoppm→tesseract 逐页草稿 + J8 导入闭环，摄取 42p，[记录](docs/quality/st-014-scanned-pdf-ocr.md)）、题库体检（ST-015，`pool_health` 纯函数+只读端点+首页卡片，J7/J7b 双引擎，[记录](docs/quality/st-015-pool-health.md)）均已实现并通过本地及远端 CI 五作业验证；含已授权的生产线文案修复（网络失败不再误报"本地服务:8000"）。ST-017 在本机生产栈实测标签化部署/回滚（构建→幂等迁移→换 api→门禁冒烟→回滚换镜像，[演练记录](docs/quality/st-017-deploy-rollback-drill.md)）。
- **ST-018（会话续答）**：`GET /api/practice/resume` 只读恢复最近未作答诊断曝光（避免刷新/重开空烧未见题），J9 双引擎通过（后端 134 passed/25 skipped，chromium 17p/3s，iPad/WebKit 20p），远端 CI 五作业全绿，生产栈已部署 `shutong-api:api-198ad7a`（`v1.6.1`）；详见 [验证记录](docs/quality/st-018-session-resume.md)。
- **ST-016（生产栈与真机 iPad 现场核对）**：经 USB Web Inspector 在真实 iPad Pro 12.9" 上完成首页/题库体检、练习判分、阶段诊断诚实对比、ST-018 续答、KaTeX 公式渲染与转义安全、PWA standalone 与本机记住令牌、断网文案核验；同步修复隧道 HTTP/2 协议、1033 自愈 watchdog 与局域网代理通道；详见 [验证记录](docs/quality/st-016-production-onsite.md)。
- **2026-11-01 运维加固**：实测排查发现宿主机重启后 `/tmp/opencode`（tmpfs）消失会导致备份 cron 外层重定向失败与 `tunnel-watchdog.sh` 状态写入失败，已统一迁移至持久化目录 `infra/.local/logs` 并验证 R2 快照恢复。

## 四科语料增量（迁移 0006）

已实现并通过后端测试：来源类别/哈希/采录与审核状态、知识点版本化与题目双向关联、勘误、覆盖缺口报告、统计型命题研究与无泄漏回测、`scripts/audit_exam_corpus.py` 只读审计。**未实现**：知识点内容播种、真题切题入库与人工审核、AI 模型推理（BLOCKED）、前端界面。详见 [四科语料增量](docs/design/four-subject-corpus.md)。

## 前端管理与使用功能物理强隔离（阶段 7，2026-11-06）

已通过 Vite MPA 多入口架构（`index.html` 与 `admin.html`）实现学生端与管理端物理脱钩。学生端彻底剥离审核台、题库体检卡片与校考录入表单；管理端工作台聚合审核台、题库体检与学校考试录入。Caddy 反代层对所有带有 `CF-Ray` 的外网隧道请求访问管理端实施 403 Forbidden 物理阻断。Playwright E2E、Vitest 及 iPadOS 模拟机主题 6 人工验收全部全绿放行。详见 [主题 6 核验清单](docs/quality/checklists/06-frontend-isolation.md)。

## 生产环境大容量存储迁移与环境隔离（阶段 8，2026-11-06）

生产根目录已平滑迁移至独立挂载大容量数据盘 `/media/xc/backup_ext4/prod-env/pageboy`。通过 `scripts/check_env_isolation.sh` 实施环境隔离自检护栏，确保开发树无生产配置密钥、无真实附件且开发用户无 docker 组提权。

## ST-020 课标与知识库条款最小整改状态（2026-11-10）

- **ST-020-RM-01（数学圆章节条款拆分与勘误）**：
  - **状态**：`CLOSED`（维持 CLOSED）
  - **验收结论**：已完成验收，圆章节 ①~⑩ 条款全集齐备，必学/选学严格区分，存量保护回归全绿；不再补包、重做或重复审核。
  - **证据位置**：`contracts/curriculum_clauses_math.json`、`services/api/tests/test_math_taxonomy_st019b.py`。
- **ST-020-RM-02（语文第四学段积累与梳理内容要求补齐与教学提示校准）**：
  - **状态**：`CLOSED`（Owner 已批准，2026-11-10）
  - **验收结论**：GPT 第二轮独立验收通过，无阻断项，无须第三轮挑战。新增 c03a 内容要求条款（全文字面值锁定）；保留并校准 c03 教学提示（记载逗号与官方分号历史差异，忠实概括五大核心要素）；知识点双向溯源 100%；定点与回归测试全绿。
  - **最终依据路径**：`/media/xc/backup_ext4/code/ShuTong_ST-020-RM-02_Review_R2.zip`（SHA256: `cef91a3b3b6f110dfba1cfc6ef855da7121c9a6bd147f601d9ce535cad0ac155`）。
- **ST-020-RM-03（语文第四学段文言文实词条款末句补齐与 ISS-EN-01A 误报纠正）**：
  - **状态**：`CLOSED`（GPT 第三轮最终验收通过，2026-11-10）
  - **验收结论**：GPT 第一轮至第三轮 Review 确认 c28 补齐、ISS-EN-01A 纠正为误报、主要证据与 SHA256 清单全项一致通过，无阻断项，闭环完成整改。
  - **最终依据路径**：`/media/xc/backup_ext4/code/ShuTong_ST-020-RM-03_Review_R3.zip`（SHA256: `06d5a36ed95a3104f92509dbfd54ad06a63a5dd9b1a0d75e9e74bc3b81f1b021`）。
- **ST-020-2A（四科知识点库全量只读审核准备）**：
  - **状态**：`CLOSED`（2026-11-11，三轮 GPT 独立审核与最终证据收口完毕）
  - **关闭依据**：经 GPT 第一轮、第二轮、第三轮独立审核及最终证据收口验收通过。四项遗留问题（A1: RM-02 归档哈希锁定为官方闭环真值 `cef91a3b...`；A2: 官方发文字号统一校准为官方印发字号 `教材〔2022〕2号`；A3: `vocabulary_req:c03a` 来源标签校准为纯 RM-02 整改验收，试点集去重后总覆盖率保持 71/241 守恒；A4: 工作区 Git HEAD、porcelain v2、二进制补丁及 `data/st020_1_negative_controls.json` 证据完整对齐）全项闭环修复。
  - **最终依据路径**：`/media/xc/backup_ext4/code/ShuTong_ST-020-2A_Closeout.md`（最终收口报告）及 `/media/xc/backup_ext4/code/ShuTong_ST-020-2A_Audit_Baseline_Review_R3.zip`（R3 审核证据包）。
- **ST-020-2B-01（三大高风险方向静态契约定点整改）**：
  - **状态**：`CLOSED`（GPT 独立复核第二轮核准通过，2026-11-11）
  - **实施内容**：
    1. 数学必学与选学切线隔离（`TASK-ERR-MA-02`）：将 `math_cand.geo.circle_tangent` 剥离选学条款 `circle:c06` 与 `circle:c07`，保留必学条款 `circle:c04`；新增独立选学节点 `math_cand.geo.circle_tangent_length`（`is_elective: true`，挂载于 `math_cand.geo.properties`），数学候选节点扩充为 48 个。
    2. 语文幽灵旧码单向清理（`TASK-ERR-CH-01, 02, 04`）：将 16 个候选节点与 22 条条款中内嵌的非法幽灵旧码单向对齐为合法存量旧码；严格保留 `critical_micro_writing` 与 `composition_expression` 待核实跨领域映射；两契约文件内幽灵旧码降为 0。
    3. 物理微观结构跨域错配清除（`TASK-ERR-PH-01`）：将 `physics_cand.matter.micro_structure` 节点的 `legacy_mapping_codes` 清空为 `[]`，消除力学密度错配。
  - **验证证据与交付依据**：
    - 64 项核心课标套件测试通过（退出码 0，5.65s）；
    - 全量后端测试：222 passed, 25 skipped（PostgreSQL 真实并发测试）, 0 failed（退出码 0，耗时 26.79s）；
    - OpenAPI 契约检查通过（`scripts/check_openapi.py`，退出码 0）；
    - 独立复核依据：`/media/xc/backup_ext4/code/ShuTong_ST-020-2B-01_Review_R2.zip`（SHA256: `9041844883fa4305905a7a8370ef944a84faa264226e44b33a5a4feb8cb62660`）。
- **ST-020-2B-02（剩余静态契约风险定点整改）**：
  - **状态**：`CLOSED`（2026-11-11，GPT R2 定点复核通过，Owner 同意关闭；不代表已合并或发布）
  - **实施内容**：
    1. 数学三元一次方程组选学隔离（`TASK-ERR-MA-01`）：将 `math_cand.eq.linear_system_3var` 的 `legacy_mapping_codes` 置为 `[]`，从 `math.eq.linear_system` 的 `target_candidate_codes` 中移除该节点，仅保留 `linear`、`linear_system` 两个原有目标，同步更新说明，实现选学物理隔离；
    2. 语文微写作跨域旧码清除（`TASK-ERR-CH-03` 修订方案 A）：清空 `critical_micro_writing` 候选中的阅读旧码为 `[]`；`composition_expression` 保留 `chinese.writing.composition`、移除 `chinese.reading.argumentative`；`critical_writing:c20` 条款原有阅读关联保留，注明仅为课标覆盖完整性映射，不得作为写作题目、成绩或画像的自动映射；独立映射表保持现状；
    3. 运行期缺口解耦：`TASK-ENG-ELEC-01..03` 单独保持 `OPEN`，零生产业务 Python、Alembic、数据库或部署修改；
    4. Scope 审计区分整改前 29 项（25 结构性、2 新设、2 待裁决）与当前 28 项（26 结构性、2 新设、0 待裁决）；数学三元方程组选学语义错误单独列账。
  - **验证证据与交付依据**：
    - 37 项核心课标套件测试通过（退出码 0，5.35s）；
    - 全量后端测试：225 passed, 25 skipped, 0 failed（退出码 0，耗时 24.23s）；
    - OpenAPI 契约检查通过（`scripts/check_openapi.py`，退出码 0）；
    - 最终复核依据：`/media/xc/backup_ext4/code/ShuTong_ST-020-2B-02_Review_R2.zip`（SHA256: `efc3f166730b06f43743d2ef6d91c09cf1ca0f955833b697b241de660aa2a0b5`）；12 契约、3 测试文件哈希守恒，离线审计 7/7 通过。
- **全科 135 个候选知识点北京市中考专家终审与虚拟信息彻底清理（2026-11-14）**：
  - **实施内容**：
    1. 北京市中考全科专家（`beijing_zhongkao_expert`）完成数学（48）、语文（25）、英语（28）、物理（34）共 135 个候选知识点的逐条 2022 课标条款溯源、北京中考题型与分值定位、必学/选学（`*`）边界核定及正式快照发布（`{subject}-v2022.1.0`）；
    2. 完成 `contracts/math_legacy_taxonomy_mapping.json` 中 `math.geo.comprehensive`（`split`）与 `math.adv.new_definition`（`retained`）两项历史映射的北京市中考专家终审裁决，`pending_human_review_count` 归零；
    3. 管理端 `KnowledgeReviewCard.vue` 增加「当前学科专家审核档案」面板并在切换节点时同步回显已保存的专家审核意见；
    4. 清理前端生产/管理界面中的“演示数据均为虚构测试数据”与虚拟占位符文案，清理开发库中残留的 `Owner`/`test` 测试审核、2018 数学真题源下误传的 6 份非真题测试 PDF 附件及孤儿文件、测试练习曝光与目标记录，并清理临时测试目录与未跟踪打包脚本。
