# 书童 Codex 交接时点的真实状态

## 提供的可运行组件

- FastAPI 私有 API（owner Bearer Token）、SQLite 本地开发适配/PostgreSQL 配置、Alembic 基础迁移。
- 来源台账、私有 PDF/图片原件与哈希、本地 PDF 文本/图片 OCR 草稿、人工确认、草稿/审核/发布选择题与修订新版本、曝光记录、自动判分、简单幂等答题、总分学校卷记录、Goal 版本、启发式画像和训练计划。
- React Web/PWA 交互骨架与三视图学习 UI（首页/练习复练/阶段诊断，Playwright J1–J4 用户旅程通过）；PWA **只缓存静态壳，不离线缓存学生数据/API**。
- OpenAPI 快照、JSON Schema 验证及反例、Markdown 图片/链接校验、测试、已验证的 GitHub CI、备份模板。

## 尚未实现且不得宣称完成

复杂试卷/公式/图表自动解析、真实资料来源法务评审、扫描 PDF 自动 OCR、四科富文本公式渲染引擎、正式目标蓝图、可比独立验证与成绩效果评价、访问身份管理、外部部署、自动告警、异地完整恢复。练习会话轮换、曝光原子化与作答幂等（ST-004）、数学纵向闭环与独立复测对比（ST-005）、学校私卷逐题人工核对与附件隔离（ST-006）、四科题型与评分来源可追溯（ST-007）、学习首页/复练/阶段诊断/缺证据解释用户旅程（ST-008）已实现并通过验证（均见下文），但小规模验证不代表吞吐达标或效果推断。

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

## ST-009 收口验证（2026-10-22）

Docs as Code/可访问性/契约与 CI 全面核对完成：README 功能清单同步、overview 审计确认、契约三次增量再生成全部一致；CI 新增 `pg-migration`（全新 PG 0001→head→downgrade 0004→head→check——ST-007 缺陷类的永久护栏，SQLite 无法拦截）与 `web-e2e` 两个作业（命令经本地等价环境逐字验证；**远端未运行不标通过**）；新增 axe-core 三视图 WCAG A/AA 扫描并修复 31 个 color-contrast serious 节点（designer 会话，仅 style.css 8 行颜色值）；ST-002 修订并发 docker 回归 6/6、ST-004 练习并发回归 19/19（跨全部五次迁移）。终验：Playwright 7/7、后端 110 passed/25 skipped、make verify、zensical --strict 全绿。**开发计划 ST-001~ST-009 全部本地验收完成**；剩余 ST-OPS-01/02 受外部环境与授权门禁约束（AC-OPS-01/02 仍未演练，真实长期数据落库前必须完成）。详见 [ST-009 验证记录](docs/quality/st-009-closure.md)。

## ST-OPS-01 本地基础工作（2026-10-22，边界如实）

按备份策略权威文档要求，`infra/backup.sh` 已扩展为 **DB+附件联合备份模板**（附件 tar.gz、双文件 SHA256SUMS、含 migration_revision 的 manifest；`BACKUP_OUTPUT_DIR` 进入本地演练模式跳过 restic——restic 本地未装）；新增隔离恢复模板 `infra/restore.sh`（SHA 校验、拒绝非 pageboy 库名/非空附件目录、pg_restore、迁移版本比对告警）与本地端到端演练 `scripts/smoke_joint_restore.py`（compose 全新双实例：种子→联合备份→摧毁→恢复→冒烟，行数/迁移版本/附件 sha 字节一致、练习可服务；orchestrator 亲跑 + lane 两轮共三次通过，清理幂等）。**这不构成 AC-OPS-01**：异地/另一故障域备份、restic 生产路径与保留策略、密钥隔离、真实 RPO/RTO 均未验证，策略状态保持 PROPOSED/UNVERIFIED。剩余 ST-OPS-01 异地部分与 ST-OPS-02 需 VPS/备份仓库/运行环境与明确授权。
