# 书童 V1.6 工程交接：从 ST-004 继续

交接日期：2026-10-18。用户要求后续所有实施任务由其他接手 agent 完成；本次只交付 handoff 和启动 prompt，不实施 ST-004 或后续功能。可直接复制的指令在 仓库根目录 `PROMPT_FOR_CODEX.md`。

> **状态更新（2026-10-19，接手 agent）**：ST-004 已实施并通过本地验收（AC-PRC-01/AC-VAL-01，含隔离 PostgreSQL 迁移往返与 19 项真并发），证据见 [ST-004 验证记录](../quality/st-004-practice-session.md)；本轮仅本地提交未推送。
> **状态更新（2026-10-21，接手 agent）**：ST-005 已实施并通过本地验收（AC-GAP-01/02/03、AC-VAL-02，compare_validation + /api/guidance/validation、纯度静态锁定、历史回放），证据见 [ST-005 验证记录](../quality/st-005-math-loop.md)；仅本地提交未推送。同日 **ST-006** 已实施并通过本地验收（AC-EVI-01/02、AC-SEC-01，school_exam_items 人工确认门禁 + 校卷附件结构性隔离，迁移 0004），证据见 [ST-006 验证记录](../quality/st-006-school-papers.md)；仅本地提交未推送。
> **状态更新（2026-10-22，接手 agent）**：**ST-007** 已实施并通过本地验收（四科题型判分矩阵、题组/阅读 group_context、听力音频复用内容附件管线、主观自评独立来源表、attempts 溯源列表，迁移 0005；含关键缺陷修复：media 列内联 FK 曾使全新 PG 库 0001 失败），证据见 [ST-007 验证记录](../quality/st-007-question-kinds.md)；仅本地提交未推送。同日 **ST-008**（三视图学习 UI + Playwright J1–J4 用户旅程 4/4，纯前端零后端改动）与 **ST-009**（README/契约核对、CI +pg-migration/web-e2e 护栏、axe-core 可访问性扫描与 31 个对比度节点修复、ST-002/004 并发回归）均已本地验收，证据见 [ST-008](../quality/st-008-user-journeys.md)/[ST-009](../quality/st-009-closure.md) 验证记录；均仅本地提交未推送。**开发计划 ST-001~ST-009 全部完成**。本文件其余内容保留为当时的交接快照，§2/§5 状态表已同步。
> **状态更新（2026-10-23，推送授权后）**：用户授权推送 `codex/st-003-private-ingestion`（`713c662` + 两个 CI 可移植性修复 `c09f925`、`8cd870c`）。远端 CI 经三轮运行稳定，[run 39898363746](https://github.com/xman900719/pageboy/actions/runs/39898363746) **四作业全绿**（api-and-docs/pg-migration/web-build/web-e2e，含 Playwright 7/7 与全新 PG 迁移往返）——至此 ST-001~009 的远端 CI 证据齐备。前两轮 web-e2e 失败原因与修复已记录于 [ST-009 验证记录](../quality/st-009-closure.md)。**PR #1 已合并入默认主干 `codex/st-001-ci`**（merge commit `964dfea`；合并后主干 CI [run 39913452863](https://github.com/xman900719/pageboy/actions/runs/39913452863) 四作业全绿；本地 `main` 已快进同步）。
> **状态更新（2026-10-24，本机部署 + Cloudflare 侧就绪）**：用户确认"仅本地主机、暂无 VPS/备份主机"。经 MCP 完成全部 Cloudflare 写入：Tunnel `shutong`（远程管理型 `fdfa8896-1f92-4dfc-8f16-fcf0055267dd`）、Public Hostname `shutong.xmanspace.asia` → 本机入口、DNS CNAME（proxied）、Access 应用 `f1149920-a808-4bae-8f88-f9f594565508` + 策略"owner only"（Allow → 账户邮箱）——经隧道访问两路径实测 302 到 Access 登录页（门禁红线生效）。本机生产栈已运行：docker compose（db=postgres:16 + api 容器 + cloudflared 容器 host 网络）+ 宿主 caddy:8180（8080 被 root 常驻 nginx 占用；api 宿主端口 18000——8000 为无关服务保留域）；`infra/compose.local.yaml` 与 `Caddyfile.local` 为本机模式工件（VPS 模板 `compose.web.yaml` 不变）。备份目标定为 **Cloudflare R2（另一故障域）**，待用户在 Dashboard 生成 S3 Token 后接通 restic 首备与演练；ST-OPS-01 异地部分仍以实际演练记录为证。

本文件是接手导航与代码快照，不取代 仓库根目录 `IMPLEMENTATION_PLAN.md`、[验收索引](../quality/acceptance.md)、[领域不变量](../design/data-model.md) 或 OpenAPI 权威契约。历史验证不能替代接手后的基线复跑。

## 1. 接手代码与 Git 边界

| 项目 | 已核实的本地快照 |
|---|---|
| 工作目录 | `/media/xc/backup_ext4/code/pageboy` |
| 当前分支 | `codex/st-003-private-ingestion` |
| 功能交接基点 | `7477df7c9240b6b84b7221a11b1ad6148d68e1b0`（ST-003） |
| 前置提交 | `8f45af3`（ST-002 功能）、`7ca9e1b`（ST-002 PostgreSQL 并发验证） |
| ST-001 收尾 | `db46f9d` |
| origin | `git@github.com:xman900719/pageboy.git` |
| 接手前工作树 | 制作本交接文档前为空；本交接将另行形成文档提交 |

**ST-002/003 尚未推送，本地 `main` 仍是早期 foundation。** 不要切回 `main` 或仅从 GitHub 克隆后开始 ST-004；先确认本地包含上述三个功能/测试提交。新机器必须取得当前分支及其提交历史，不能以远端缺少代码为由重写已完成功能。若代码尚不可访问，报告缺少的提交，等待用户提供本地仓库副本或明确授权的传输方式；本文件不授予 push 权限。

可从包含本交接文档的当前分支新建本地 ST-004 分支；保留已有分支和他人修改。远端分支状态在本次交接中没有 fetch 或重新查询；本地 tracking ref 不能证明远端当前状态。ST-001 的既有远端 CI 证据不覆盖 ST-002/003 或本次文档。

## 2. 已完成与证据范围

| 任务 | 状态 | 证据与限制 |
|---|---|---|
| ST-001 | 已完成本地基线及当时的远端 CI | [ST-001 记录](../quality/st-001-baseline.md)，仅改 AGENTS.md 的触发验证已通过 |
| ST-002 | 本地验收完成 | [ST-002 记录](../quality/st-002-question-revisions.md)，不可变修订、旧历史保留；6 轮真实 PostgreSQL 修订并发通过，远端 CI 未运行 |
| ST-003 | 本地验收完成 | [ST-003 记录](../quality/st-003-private-ingestion.md)，来源台账、私有原件、哈希、本地 PDF 文本/图片 OCR、人工确认及发布门禁；远端 CI 未运行 |
| ST-004 | 本地验收完成 | [ST-004 记录](../quality/st-004-practice-session.md)，练习会话/轮换、曝光原子化（部分唯一索引）、作答幂等并发（隔离 PG 16.15 迁移往返 + 19 项真并发零 500）；远端 CI 未运行 |
| ST-005 | 本地验收完成 | [ST-005 记录](../quality/st-005-math-loop.md)，数学纵向闭环、compare_validation 纯函数、guidance 纯度静态锁定、历史回放不可变；OpenAPI 已重新生成校验；远端 CI 未运行 |
| ST-006 | 本地验收完成 | [ST-006 记录](../quality/st-006-school-papers.md)，学校私卷逐题人工确认门禁（ocr_draft 未确认不产生证据）、总分不折算、校卷附件无字节路由/存储键不外泄；迁移 0004 SQLite+PG16 验证；远端 CI 未运行 |
| ST-007 | 本地验收完成 | [ST-007 记录](../quality/st-007-question-kinds.md)，四科题型判分矩阵（短答归一化/主观自评独立来源表）、题组 group_context、听力音频复用内容附件、attempts 溯源列表；迁移 0005 PG16 验证（含全新库 0001 关键缺陷修复）；ST-004 并发全量回归；远端 CI 未运行 |
| ST-008 | 本地验收完成 | [ST-008 记录](../quality/st-008-user-journeys.md)，三视图学习 UI + Playwright J1–J4 用户旅程 4/4（chromium）；诚实文案红线零违规；零后端改动；远端 CI 未运行 |
| ST-009 | 本地验收完成 | [ST-009 记录](../quality/st-009-closure.md)，README/契约核对、CI +pg-migration/web-e2e 护栏（远端未运行）、axe-core 扫描 + 31 对比度节点修复、ST-002/004 并发回归全绿；**开发计划完成** |
| 完整 MVP / 生产就绪 / 灾备 | 未完成 | 后续任务、完整联调与真实异地恢复不得按上述单项结果推定完成 |

制作交接时，已重新执行 `PATH="$PWD/.venv/bin:$PATH" make verify`：API/业务 **56 passed、6 skipped**；文档检查器 **2 passed**；JSON Schema 正反例、24 篇 Markdown、OpenAPI 一致性通过。文档修改后的检查结果见本文件末尾。6 项 skipped 是可选 PostgreSQL 修订并发测试，不是普通门禁已执行的并发证据。

以下为 ST-003 阶段的历史实测，本次文档交接没有重跑：

- 独立 PostgreSQL 16.15：修订并发 6 轮，每轮 8 个真实 HTTP 请求、8 个连接，冲突重试成功，旧历史不变。**不覆盖曝光或作答并发。**
- SQLite 临时库 `0001 → 0002 → 0001 → 0002`、PostgreSQL 临时库 `0001 → 0002` 与结构检查通过，原来源保留。
- Python 3.12 本地容器构建、OpenAPI 一致性、临时 SQLite 迁移、uid 10001 私有文件写入及 PNG/JPEG 实际 OCR 通过；无完整 Compose/生产联调。
- Zensical 严格构建通过；Web 构建的已有证据来自 ST-001，本次未重新构建前端。

既有警告：Starlette/httpx 弃用警告；ST-001 Actions 曾有 Node 20 运行时弃用提示。记录真实失败，不为消除警告顺手升级全套依赖。

## 3. 接手顺序与执行命令

1. 读 `AGENTS.md`、本文件、`CODEX_START_HERE.md`、`PROJECT_STATUS.md`、`IMPLEMENTATION_PLAN.md`，再按当前任务读取 `docs/design/`、`docs/quality/acceptance.md` 与 `contracts/`。当前未配置 `.agent/policies/`，不得声称已加载不存在的策略。
2. 检查工作树、分支和基点，保留所有他人修改。复跑基线并记录通过、失败、未验证；先解释与历史计数的差异，再实施。
3. 对 ST-004 写出“目标 / 不变项 / 步骤 → 验证”的短计划，先用反例复现竞争，再做最小修改和真实数据库验证。
4. 每个任务独立验证、同步契约/文档并本地提交；通过后按依赖推进下一项。环境、权限或需求缺口实质阻塞时报告准确边界，不绕过门禁。

已有根目录 `.venv`；新环境可建立虚拟环境后安装 `./services/api[test]`、`requirements-tools.txt`，文档站点需 Zensical。本地解析依赖 Poppler 与 Tesseract（`chi_sim`、`eng`）；不要把缺工具导致的失败当成业务失败，也不要悄悄跳过正例解析测试。

```bash
# 从仓库根目录执行；均不推送远端
git status --short
git branch --show-current
git log -6 --oneline
git merge-base --is-ancestor 7477df7 HEAD
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
# 可选集成回归：需要 Docker，只创建/清理其自身临时 PostgreSQL 容器
.venv/bin/python scripts/test_revision_concurrency.py
# 只有修改 API 后才生成，再验证快照
.venv/bin/python scripts/generate_openapi.py
.venv/bin/python scripts/check_openapi.py
```

`make verify` 不包含前端构建、完整文档站点、可选 PostgreSQL 测试、生产联调或恢复演练。前端发生改动时再执行 `cd apps/web && npm ci && npm run build`，并按 ST-008 补充用户旅程验证。不要直接对未知 `DATABASE_URL` 执行迁移；迁移测试必须使用本次拥有的隔离库。ST-003 容器检查命令见其验证记录，脚本为 `scripts/smoke_ingestion_container.py`。

## 4. ST-004 第一执行包（已于 2026-10-19 实施并本地验收）

> 本节保留为交接时的需求快照。实施结果与全部验证证据见 [ST-004 验证记录](../quality/st-004-practice-session.md)：最小无状态会话与轮换规则、`exposures.question_id` + 部分唯一索引 `uq_exposure_first_unseen`、`answer_attempts.uq_attempt_exposure`、迁移 `0003`（条件式 + 回填 + 诚实失败），SQLite 单线程与 PostgreSQL 真并发（natural+colliding）均通过。

目标：练习会话、稳定题目轮换、原子曝光、幂等提交与真实并发验证。验收沿用 **AC-PRC-01、AC-VAL-01**。以下是接手时需要验证的工作项，不是已确定的数据结构或已完成测试。

### 已查证的代码入口

| 文件 / 入口 | 现状与接手用途 |
|---|---|
| `services/api/shutong/main.py`：`next_item` | 查询最新发布版后逐题查曝光、再插入；training 当前会反复取排序首题，未见判断与插入没有并发原子保证 |
| 同文件：`submit_attempt` | 先查幂等键及曝光已有作答，再插入；需验证并发相同键和不同键竞争同一曝光的行为 |
| `services/api/shutong/models.py` | Exposure/AnswerAttempt；已有 `(learner_id, client_attempt_id)` 唯一约束，不能以先查询代替数据库约束与竞争处理 |
| `services/api/shutong/schemas.py` | 当前输入/输出定义，新增会话与幂等契约需在此和 OpenAPI 同步 |
| `services/api/tests/test_api.py` | 当前单线程幂等与未见题测试 |
| `services/api/tests/test_question_revisions.py` | 新版选择、跨版本曝光、旧版答题历史回归 |
| `services/api/tests/test_revision_concurrency.py` | 可参考真实 HTTP、独立连接、同步竞争与历史快照的测试手法；不可直接作为 ST-004 证据 |
| `services/api/alembic/versions/` | 当前 head 为 `0002`；结构变更须追加显式迁移 |

### 最低验证矩阵

| 场景 | 必须证明的行为 |
|---|---|
| 正常会话与轮换 | 定义并记录最小会话/轮换规则；多题池不再始终返回首题，排除未发布题并遵循最新发布版本规则 |
| evaluation 首曝竞争 | 多个真实并发请求不能把同一学习者的同一逻辑题重复认定为独立未见题；以落库记录和响应共同断言 |
| 跨版本已见 | 任一版本已曝光，更正发布的新版本仍不能恢复未见资格；旧曝光/作答不改写 |
| 幂等键相同、载荷相同 | 并发重试最终只有一条有效作答，返回同一持久结果，不出现唯一冲突引发的未处理 500 |
| 幂等键相同、载荷不同 | 拒绝复用键；不得静默覆盖原答题或分数 |
| 同一曝光、不同幂等键 | 并发提交最多产生一条有效作答，失败事务无残留 |
| 权限、耗尽与过滤 | 未认证、非 owner 记录、无合格题、知识点过滤与训练/评价隔离有明确正反例 |
| 迁移与回归 | SQLite 开发适配、PostgreSQL 真实行为一致于契约；已有题目、导入追溯、历史评分保持 |

真实并发需使用独立数据库连接和真实 HTTP 请求，记录数据库版本、轮数、请求数、连接数、状态分布、最终行数及清理结果。测试要能暴露竞争窗口，不能只依赖线程启动，也不能把 mock、顺序请求或 SQLite 单连接当作 PostgreSQL 并发通过。小规模并发正确性验证不等于生产吞吐或压测达标。

不变项：保持 FastAPI 模块化单体，`guidance.py` 纯计算，旧版本/历史不可变、学校总分不产生考点分；不借此重做身份系统、OCR、四科评分或生产部署。会话最小语义、兼容方式和迁移/应用回退方案须先依据现有客户端与契约明确；不要预建通用调度/插件框架。

## 5. 后续全部任务的接手路线

| 顺序 / 任务 | 执行目标与验收入口 | 当前状态 |
|---|---|---|
| ST-004 | 会话、轮换、曝光原子化、作答幂等；AC-PRC-01、AC-VAL-01 | 已完成（本地验收，[证据](../quality/st-004-practice-session.md)） |
| ST-005（ST-004 后） | 数学目标→证据→画像→差距→计划→独立复测；AC-GAP-01/02/03、AC-VAL-02，含纯函数依赖与历史回放 | 已完成（本地验收，[证据](../quality/st-005-math-loop.md)） |
| ST-006（ST-005 后） | 学校私卷、逐题人工核对；AC-EVI-01/02、AC-SEC-01，不能复用内容发布权限 | 已完成（本地验收，[证据](../quality/st-006-school-papers.md)） |
| ST-007（ST-005 后） | 四科题型、公式/图表/阅读/音频/主观自评；评分来源与样例可追溯 | 已完成（本地验收，[证据](../quality/st-007-question-kinds.md)） |
| ST-008（ST-005 后） | 首页、复练、阶段诊断、缺证据解释；真实用户旅程与 Playwright | 已完成（本地验收，[证据](../quality/st-008-user-journeys.md)） |
| ST-009（持续） | Docs as Code、UX/可访问性、契约与 CI；跟随每项变更同步 | 已完成（收口核对 + 新增护栏，[证据](../quality/st-009-closure.md)；远端 CI 作业未运行） |
| ST-OPS-01（首次真实长期数据前） | 私有部署、异地加密 DB+附件协调备份、独立恢复；AC-OPS-01/02 | **本地部分已完成**（联合备份模板 + restore.sh + 本地隔离演练三跑通过，[backup-policy 事实记录](../operations/backup-policy.md)）；**异地/AC-OPS-01 仍未演练**——需 VPS/备份仓库/密钥隔离等外部环境与明确授权，真实长期数据落库前必须完成 |
| ST-OPS-02（依赖实际运行环境） | 监控、告警、更新回滚与故障模拟 | 未实施/未演练；运行环境就绪后执行 |

默认顺序为 ST-004 → ST-005 → ST-006 → ST-007 → ST-008，ST-009 随任务同步；ST-OPS-01 的真实数据门禁优先于任何真实长期使用，ST-OPS-02 在相应运行环境就绪后执行。任务范围和验收 ID 始终以实施计划/验收索引为准；需要变更时同步权威文档，不在 handoff 中另建第二套任务清单。

## 6. 安全、迁移与未验证边界

- 只用明确标记“虚构测试数据”的原卷/题目，不把私有文件、数据库、备份或凭据提交 Git。
- 当前 owner token 只适合隔离私网；不能因此开放公网。学校原件、画像和答题不能经内容目录传播。
- ST-003 仅实现 PDF 文本与 PNG/JPEG OCR 草稿；扫描 PDF 自动 OCR、复杂版面/公式、审核 UI 和真实 OCR 准确率未完成/未评估。人工确认和来源权限标注不是法律结论。
- `infra/backup.sh` 仍只覆盖 DB，不包含原件联合备份。持久目录/卷不是备份；RPO/RTO 仍 UNVERIFIED，唯一策略在 [backup-policy.md](../operations/backup-policy.md)。
- `0002` 新表和私有原件需保留；旧应用不了解导入门禁，应用回退时不能继续发布带附件来源。新增迁移须验证已有库升级，不对真实库执行删表降级。
- 本交接不授权 push、远端写入、部署、生产容器/数据库操作、删除卷或备份。过去 ST-001 推送验证的授权不能扩大到后续任务。无需反复确认可逆本地开发；确需外部授权时先完成可审阅的本地结果，再准确说明待授权动作。

## 7. 每项交付与下一次交接

接手 agent 对每个任务执行：基线 → 失败反例 → 最小实现 → 相关正反例 → 必要上层门禁 → 同步文档/契约/迁移 → 独立本地提交。最终只报 **结果 / 范围 / 验证证据 / 剩余事项**，附实际命令、计数、失败归因、未验证项、提交 SHA 和下一任务 ID。未运行的远端 CI、生产/灾备或性能验证不能记为通过。

如由多个 agent 继续，各任务指定唯一负责人；同一数据结构/API 不并发修改，必要的只读复核可独立进行。任何接手 agent 都不得覆盖其他 agent 的未提交修改。下一次切换 agent 时更新本交接的接手点和证据链接，保留各任务原始质量记录。

## 本次交接文档验证

- 修改前 `PATH="$PWD/.venv/bin:$PATH" make verify`：API 56 passed、6 skipped；文档检查器 2 passed；Schema、24 篇 Markdown、OpenAPI 一致性通过。
- 修改后 `.venv/bin/python scripts/check_docs.py`：25 篇 Markdown 链接/图片检查通过；`.venv/bin/python -m pytest scripts/test_docs_checker.py -q`：2 passed。
- `.venv/bin/zensical build --strict`：初次因两处站点外 Markdown 链接失败；改为明确的仓库路径引用后通过。
- `git diff --check`：通过。本轮只改交接文档、prompt 和导航；业务代码、API 契约、迁移不变。PostgreSQL 并发、容器、前端、远端 CI 与恢复演练本轮未重跑。
