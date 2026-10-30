# 书童 V1.6 → 可交付 MVP · Codex 实施任务

> 依据 `docs/quality/acceptance.md` 中的唯一验收 ID。每个任务独立形成可回顾的 Git 提交；不预先实现尚未得到真实需求支持的复杂抽象。

| ID | 顺序 | 目标与产出 | 验收与门槛 |
|---|---|---|---|
| ST-001 | P0 | 安装基线依赖、现有测试与文档/契约 CI、消除失败与不一致 | AC-DOC-01/02/03，CI 可重复运行 |
| ST-002 | P0 | 已发布题修改生成新 QuestionVersion；保留原版 | AC-CNT-02，新旧答题历史不变 |
| ST-003 | P0 | 来源台账、附件上传/校验、PDF/图片解析草稿、人工确认工作流 | AC-CNT-01/03，文件哈希与私有 ACL |
| ST-004 | P0 | 练习会话、题目轮换、曝光原子化、幂等与并发验证 | AC-PRC-01、AC-VAL-01，并发测试 |
| ST-005 | P0 | 数学单学科 目标→事实证据→画像→差距→计划→未见题复测 | AC-GAP-01/02/03，AC-VAL-02 |
| ST-006 | P1 | 私人学校试卷上传、逐题得分确认（OCR 可选） | AC-EVI-01/02，AC-SEC-01 |
| ST-007 | P1 | 四科题型组合：题组、公式、图表、阅读、音频/主观自评 | 四科样例和评分来源可追溯 |
| ST-008 | P1 | 精简学习首页、复练、阶段诊断、缺证据解释 | 关键用户旅程 Playwright 通过 |
| ST-009 | P1 | 完整 Docs as Code + UX/可访问性、站点构建、自动化更新契约 | 全部链接/契约/CI 检查通过 |
| ST-010 | P2 | iPad（WebKit 仿真）e2e 通道：既有 J1–J4/a11y 全套在 iPad 描述符下重放 + 720–980px 响应式断言 + gen 11/Mini/Pro 11 矩阵 | iPad 通道 10/10、chromium 回归 7 passed + 3 skipped |
| ST-011 | P1 | 人工审核 UI（审核台：题源台账→来源审核→附件→确认导入→草稿审核→发布）+ 草稿只读端点 | UI 旅程 J5 双引擎通过；AC-CNT-01/03 补充 UI 证据 |
| ST-012 | P2 | iPad PWA 应用化：主屏幕 PNG 图标 + 令牌门选配「在本机记住令牌」（默认仅内存红线保留，所有者授权修订） | J6 双引擎通过（冷启动免输入/退出清除/失效拦截正反例） |
| ST-013 | P1 | 题干富文本与公式渲染：`$…$`/`$$…$$` LaTeX 片段在教学 UI 与审核台安全渲染（转义优先、无原始 HTML 通道） | 渲染纯函数单测正反例 + 公式题 e2e 双引擎断言（chromium/iPad-WebKit） |
| ST-014 | P1 | 扫描 PDF 自动 OCR 摄取：无文本层 PDF 走 pdftoppm→tesseract 逐页草稿，parser_version 如实记录双工具 | 图像型 PDF 摄取正例 + 文本 PDF 不降级反例；本地 e2e 摄取测试 |
| ST-015 | P2 | 题库体检（纯函数 + 只读端点 + 首页卡片）：按知识点发布量/未见题存量/曝光覆盖如实报告，不制造分数 | 空池/单题/充足三态正反例；端点契约与 OpenAPI 再生成校验 |
| ST-016 | P1 | 生产栈现场校验：线上 URL（Tunnel+Access 后）响应、构建产物一致性、PWA 静态壳在 iPad/WebKit 注册与缓存 | curl 实测记录 + WebKit e2e 断言；真实 iPad 人工核对清单交付 |
| ST-018 | P1 | 会话续答：刷新/重开恢复最近未作答曝光，避免 iPad 上未见题空烧 | 端点正反例 + J9 双引擎（claim→刷新→同题恢复→答完→刷新→无残留） |
| ST-OPS-02 | P1 | 主机监控、告警与更新回滚流程 | 模拟备份失败和错误镜像能恢复 |

## 执行记录

- ST-018：本地验收完成（2026-10-29），会话续答——`GET /api/practice/resume` 只读恢复最近未作答**诊断**曝光（训练不恢复：无状态成本），J9 双引擎（chromium 17p/3s、iPad 20p）；[验证记录](docs/quality/st-018-session-resume.md)。首版误启训练续答导致 e2e 文案级联失败，按产品语义收窄并补反例锁定。
- ST-013：本地验收完成（2026-10-29），题干富文本与公式渲染——KaTeX `$…$`/`$$…$$` 安全渲染（纯函数切分 + 文本转义 + 仅 KaTeX HTML 注入），单测 9/9、chromium 13 passed/3 skipped、iPad/WebKit 16 passed；附生产线文案缺陷修复（api.ts 网络失败误报"本地服务"）；[验证记录](docs/quality/st-013-formula-rendering.md)。零后端/契约变更。远端 CI 待推送后验证。
- ST-014：本地验收完成（2026-10-29），扫描 PDF 自动 OCR 摄取——无文本层 PDF 走 pdftoppm→tesseract 逐页草稿（页码标记、双工具版本如实记录、混合版式为已知限制），摄取测试 42 passed、全量 127 passed/25 skipped；[验证记录](docs/quality/st-014-scanned-pdf-ocr.md)。无 Schema/迁移/契约变更。
- ST-015：本地验收完成（2026-10-29），题库体检——`pool_health` 纯函数 + `GET /api/guidance/pool-health` + 首页「题库体检」卡片（J7/J7b 双引擎，chromium 15p/3s、iPad 18p）；OpenAPI 再生成校验；[验证记录](docs/quality/st-015-pool-health.md)。
- ST-017（ST-OPS-02 的更新/回滚部分）：本机生产栈实测完成（2026-10-29）——标签化部署/回滚脚本 + `/health/live` 构建身份，drill-a/drill-b 部署与回滚、legacy 内容探针、数据一致性核对全绿；schema 降级回滚设计上排除；[演练记录](docs/quality/st-017-deploy-rollback-drill.md)。
- ST-016：验收完成（2026-10-30）——环回栈/线上门禁/真机 iPad 全链核对（首页、题库体检数字、练习判分、阶段诊断与诚实对比、ST-018 续答实测、KaTeX 公式渲染与转义安全、PWA standalone 与记住令牌、断网文案构建级验证）；过程修复隧道 QUIC→HTTP/2、1033 自愈 watchdog、iPad 网络到 Access 登录域的代理通道；[验证记录](docs/quality/st-016-production-onsite.md)。遗留：owner 目视复核横竖屏/分屏、iPad 入网持久方案（三选一，待 owner 决定）。
- ST-001：已完成。修复前端类型与文档站点链接问题，本地与远端基线均通过；[验证记录](docs/quality/st-001-baseline.md)。AC-DOC-01/02/03 均通过；仅修改 AGENTS.md 的独立提交 `4a5dd6f` 已实际触发 [push CI](https://github.com/xman900719/pageboy/actions/runs/39117777469)，两个作业全部成功。后续开发从 ST-002 开始。

- ST-002：本地验收已完成，AC-CNT-02 正反例及 PostgreSQL 真实并发验证通过（6 轮 × 8 请求、独立连接）；[验证记录](docs/quality/st-002-question-revisions.md)。本轮仅本地提交，远端 CI 未运行。后续 ST-003 见下条。

- ST-003：本地验收完成，来源台账、私有原件/哈希、PDF 文本/图片 OCR 草稿及人工确认通过 AC-CNT-01/03 范围测试；[验证记录](docs/quality/st-003-private-ingestion.md)。学校私卷、扫描 PDF 自动 OCR、审核 UI 和联合备份不在本项完成范围；远端 CI 未运行。下一项 ST-004。
- ST-004：本地验收完成，练习会话/轮换、曝光原子化（部分唯一索引跨版本防重复未见首曝）、作答幂等约束化通过 AC-PRC-01/AC-VAL-01 范围验证——隔离 PostgreSQL 16.15 迁移往返 + 19 项真并发（8 请求/8 独立连接/轮，零 500）；[验证记录](docs/quality/st-004-practice-session.md)。吞吐压测、远端 CI、前端用户旅程不在本项范围。下一项 ST-005。
- ST-005：本地验收完成，数学纵向闭环通过 AC-GAP-01/02/03、AC-VAL-02 范围验证——compare_validation 纯函数 + /api/guidance/validation；纯度 AST 静态锁定、历史回放不可变、纵向闭环正反例（12 项新测试）；OpenAPI 重新生成校验；[验证记录](docs/quality/st-005-math-loop.md)。效果推断/跨时间保持/题型难度匹配不在本项范围；远端 CI 未运行。下一项 ST-006。
- ST-006：本地验收完成，学校私卷通过 AC-EVI-01/02、AC-SEC-01 范围验证——school_exam_items 人工确认门禁 + school_paper_attachments 结构性隔离（17 项新测试 + Gate 整改 1 项）；SQLite 往返 + PG16 一次性迁移腿；OpenAPI 重新生成校验；[验证记录](docs/quality/st-006-school-papers.md)。OCR 分数表解析、附件浏览端点不在本项范围；远端 CI 未运行。下一项 ST-007。
- ST-007：本地验收完成，四科题型与评分来源可追溯通过计划行范围验证——kind 判分矩阵（短答归一化/主观自评独立来源表不进客观证据）、题组 group_context、听力音频复用内容附件管线（无新字节路由）、attempts 溯源列表（14 项新测试 + Gate 整改 2 项）；PG16 迁移腿捕获并修复关键缺陷（内联 FK 使全新 PG 0001 失败——SQLite 掩蔽）；ST-004 并发脚本全量回归通过；[验证记录](docs/quality/st-007-question-kinds.md)。富文本渲染/前端旅程属 ST-008；音频转写不做；远端 CI 未运行。下一项 ST-008。
- ST-008：本地验收完成，精简学习首页/复练/阶段诊断/缺证据解释通过 Playwright J1–J4 用户旅程（4/4，chromium 10.9s；双 webServer 临时 SQLite + 同源代理；种子全部虚构测试数据）；零后端改动（110 项护栏不变）；诚实文案红线 grep 零违规；[验证记录](docs/quality/st-008-user-journeys.md)。单浏览器、无性能断言；远端 CI 未运行。下一项 ST-009 收口。
- ST-009：本地验收完成，Docs as Code/契约核对与 README 同步、CI 新增 pg-migration+web-e2e 护栏（命令本地逐字验证、远端未运行）、axe-core 三视图可访问性扫描与 31 个对比度节点修复、ST-002/004 并发回归全绿；[验证记录](docs/quality/st-009-closure.md)。**开发计划 ST-001~ST-009 全部完成**；剩余 ST-OPS-01/02 待外部环境与授权。
- ST-OPS-01（本地部分）：联合备份模板（backup.sh 附件协调）+ restore.sh + 本地隔离恢复演练三次通过（行数/迁移版本/附件字节一致）；**不构成 AC-OPS-01**——异地/另一故障域、restic 生产路径、保留/告警、真实 RPO/RTO 未验证（见 PROJECT_STATUS 与 backup-policy 事实记录）；异地部分与 ST-OPS-02 待外部授权。
- ST-010：本地验收完成，iPad（WebKit 仿真）e2e 通道——`E2E_DEVICE=ipad`（`npm run test:e2e:ipad`）经 devices['iPad (gen 7)']（810×1080、hasTouch、isMobile）整套切换到 WebKit：J1–J4 用户旅程、a11y 三视图扫描与新增 R1/R2/R3 响应式断言全绿（10/10，26.4s）；chromium 通道回归 7 passed + 3 skipped（R1–R3 按设计仅 iPad 通道运行）。R1 竖屏 810px 落 720–980 区间且 .home-grid 保持 grid（断点未触发）、三视图零横向溢出；R2 横屏 .page 被 max-width 980px 精确收束；R3 把 gen 11/Mini/Pro 11 竖横六向矩阵入册门禁。零后端/零前端 src 变更（测试基建）；WebKit 系统库经 install-deps 补装闭环；CI 新增 web-e2e-webkit 作业并随 `86d5e3c` 推送实测[五作业全绿](https://github.com/xman900719/pageboy/actions/runs/40178219352)（web-e2e-webkit 10 passed/1.4m）；[验证记录](docs/quality/st-010-ipad-emulation.md)。
- ST-011：本地验收完成，人工审核 UI（审核台第 4 视图）+ 草稿只读端点 `GET /api/admin/sources/{id}/questions`（QuestionVersionOut，补齐审核 UI 无法回显草稿的契约缺口；API 全量 112 passed、OpenAPI 再生成零漂移）。审核台五段工作流（台账/来源人工审核显式勾选门禁/附件上传解析含复位警示/逐题录入确认导入/草稿审核发布按来源状态如实禁用）经 **J5 全闭环旅程**双引擎通过——chromium 9 passed + 3 skipped、iPad/WebKit 12 passed；A4 审核台 axe 扫描 0 违规；R1 扩展至四视图零溢出。读码实证并修复 designer 交付中的两处缺陷（确认导入 source_document_id 误填附件 id 恒 409；版本卡片陈旧重载依赖）。J5 走合成音频路径使 CI web-e2e 作业无解析器依赖；推送 `ca0300b` 实测[五作业全绿](https://github.com/xman900719/pageboy/actions/runs/40248302508)（chromium 9 passed + 3 skipped、iPad/WebKit 12 passed，J5/A4 首次远端运行）；[验证记录](docs/quality/st-011-admin-review-ui.md)。
- ST-012：本地验收完成，iPad PWA 应用化——PNG 主屏幕图标（`7de7584`，iPadOS 不认 SVG 图标；apple-touch-icon/manifest/sw v2，Playwright 栅格化全出血避免双重圆角）+ 令牌门**选配**「在本机记住令牌」（ST-008「令牌仅内存」红线经所有者明确授权的修订，如实标注：默认仍仅内存、显式勾选才写本机、退出即清、失效自动清、值不出设备、服务仍在 Cloudflare Access 之后）。J6 四相旅程（记住→冷启动免输入直达→退出清除→失效拦截+偏好撤销）chromium 10 passed + 3 skipped、iPad/WebKit 13 passed；宿主栈实测 `/icon-180.png` 200；推送实测[五作业全绿](https://github.com/xman900719/pageboy/actions/runs/40425018843)（WebKit 13 passed/1.9m，J6 远端首跑即绿）；[验证记录](docs/quality/st-012-pwa-remembered-token.md)。

## 阶段门禁

- **Gate A（可安全开始开发）**：测试/迁移/契约/文档 CI 可重复；没有真实原卷或密钥提交 Git。
- **Gate B（内容可用）**：真题仅在完成来源与人工审核后发布；学生私卷无法被题库 API 查询。
- **Gate C（核心学习可用）**：学校总分不制造知识能力；证据不足不计算虚构分数；训练题不能充当独立未见题。
- **Gate D（真实个人长期使用）**：可从**另一故障域**的密文备份，在独立环境完整恢复 DB + 附件并通过端到端冒烟检查。

## 任务依赖

ST-001 → ST-002、ST-003 → ST-004 → ST-005 → ST-006、ST-007、ST-008；ST-OPS-01 在首次真实数据落库前单独完成；ST-009 与所有契约变动持续并行。

## 明确暂不实现

中考成绩预测、BKT/IRT 标定、复杂 AI Agent、商业账号体系、公开试卷分发、自动全网爬取、Graph DB、多节点双活、容器编排集群、自动作文最终评分、全功能离线答题。这些只能在实际需求和数据证据出现后，通过 ADR 增补。
