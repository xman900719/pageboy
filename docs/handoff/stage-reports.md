# 自规划开发阶段汇总报告（长任务日志）

> 本文件是「agent 自行规划优化/新功能 → 交付生产可用书童」长任务的阶段汇总日志。
> 每个阶段结束追加一节：结果 / 范围 / 验证证据（实际命令与计数）/ 剩余事项与下一阶段。
> 任务级验收证据仍以 `docs/quality/` 各 ST 记录为准，本日志不做第二套验收口径。

## 阶段 0 · 基线盘点与阶段规划（2026-10-29）

**结果**：确认仓库处于 ST-001~ST-012 全部本地+远端 CI 验收完成的状态（本地分支 `codex/st-003-private-ingestion` 领先远端 1 个文档提交；远端默认主干 `codex/st-001-ci` 对应 PR #1 合并态）。生产栈（db+api+cloudflared）已运行约 11 小时，caddy 宿主入口 8180 正常；R2 异地备份 cron 当日 16:00 成功（restic 快照 + check 通过）。验收索引中 AC-OPS-01/02 已达成。

**范围**（未改代码）：复跑基线、盘点生产库、盘点线上入口、规划后续阶段。

**验证证据（实际命令）**：
- `PATH="$PWD/.venv/bin:$PATH" make verify`：API/业务 **112 passed、25 skipped、0 failed**；契约正反例 PASS；35 篇 Markdown PASS；文档检查器 2 passed；OpenAPI 一致性 PASS。
- 生产库计数（只读，不显示内容）：questions=21、question_versions=21、exposures=2、answer_attempts=0、source_documents=6、source_attachments=1、school_exams=0、goals=4；migration head=0005。**真实学习数据尚未开始积累（0 条作答）**——生产可用性取决于" owner 能顺畅导入真实卷并完成每日循环"，而非数据修补。
- 线上入口：`curl https://shutong.xmanspace.asia/`、`/icon-180.png`、`/sw.js` 均 **302 → Cloudflare Access 登录页**（门禁红线生效，公网不可绕过；应用内容无法在无凭证下从外部核验）。
- 本机生产栈（不经 Access）：`/health/live`、`/health/ready`、`/api/subjects`（Bearer）、web root、manifest 全部 200。

**剩余事项与下一阶段**：按 IMPLEMENTATION_PLAN.md 新增 ST-013~ST-017 任务行推进——ST-013 公式渲染（前端）、ST-014 扫描 PDF OCR（后端）、ST-015 题池体检（后端）、ST-016 生产栈现场校验、ST-017/ST-OPS-02 部署回滚演练。iPad 测试面说明：本环境无法驱动真实 iPad，测试面为 Playwright **iPad(gen 7)/WebKit 仿真通道**（Safari 同引擎、触摸、810×1080）＋ 本机生产栈 + 线上 URL 可达性核验；真机核对清单在 ST-016 交付给 owner 执行。

## 阶段 1 · ST-013 公式渲染 + ST-014 扫描 PDF OCR（2026-10-29 完成）

**结果**：两个并行开发 lane 交付并由编排者逐项复验。ST-013：题干/选项/阅读材料/参考答案/审核台预览全部经 KaTeX 安全渲染（`$…$`/`$$…$$`；文本段 React 自动转义，只有 KaTeX 生成 HTML 注入；不配对/空公式字面回退）；附加授权修复线上文案缺陷（网络失败误报"本地服务 :8000"）。ST-014：无文本层 PDF 摄取自动走 pdftoppm→tesseract 逐页 OCR 草稿（页码标记、双工具版本如实记录），仍以人工确认为门禁。

**范围**：前端（rich.tsx/rich.test.ts/QuestionCard/QuestionVersionsCard/style.css/formulas.spec.ts/api.ts 文案 + 依赖 katex/vitest）；后端 ingestion 解析路径（private_files.py + test_ingestion.py）；设计/验收文档同步。零后端契约变更。

**验证证据（复验实测）**：
- `npm run test:unit` 9 passed；`npm run build` 通过（KaTeX 字体随构建打包）。
- `npx playwright test`：**13 passed / 3 skipped**（chromium，含新增 formulas 3/3）；`npm run test:e2e:ipad`：**16 passed**（WebKit/iPad gen 7，formulas 3/3 同绿）。
- `services/api` 全量：**127 passed / 25 skipped / 0 failed**（基线 112 + ST-014 五项 + ST-015 八项 + ST-017 两项）；摄取专项 42 passed。
- 契约/文档门禁：validate_contracts、check_docs（40 篇）、check_openapi、`zensical build --strict` 全 PASS。
- ST-014 OCR 样例（合成 2 页图像 PDF）：页码标记 + 自绘文本往返成功，parser_version 记录 `pdftotext … + tesseract 5.5.0 (ocr fallback)`。

**剩余事项**：ST-013/014/015 提交 `c429910`/`0656cb4`/`94316ee`；ST-017 演练记录提交后统一推送并核对远端 CI（iPad e2e 作业首次包含公式/题池断言）。

## 阶段 2 · ST-015 题库体检 + ST-017 部署/回滚演练（2026-10-29 完成）

**结果**：题库体检（后端纯函数 + 只读端点 + 首页卡片）上线；本机生产栈完成标签化部署/回滚实测。

**范围**：guidance.py 纯函数、`GET /api/guidance/pool-health`、HomeView/PoolHealthCard、J7/J7b e2e、OpenAPI 再生成（+39）；infra/deploy.sh、infra/rollback.sh、compose 镜像标签与 `SHUTONG_APP_REVISION` 透传、`/health/live` 构建身份、CI web-e2e 增加 vitest 步骤。

**验证证据（复验实测）**：
- 后端单测：test_pool_health 8 passed + test_health_revision 2 passed；全量 127 passed/25 skipped。
- 前端双引擎：chromium **15 passed / 3 skipped**、iPad/WebKit **18 passed**（J7/J7b 同绿）。
- 部署演练（docs/quality/st-017-deploy-rollback-drill.md）：部署 drill-a → drill-b → 无参回滚 drill-a → 状态文件往返 → legacy 内容探针（docker inspect 证实镜像切换、旧构建无 app_revision）→ 收尾 drill-a；全程 smoke 全绿；演练前后 DB 计数（21/2/1）与附件 sha 逐项一致；`--web` 重建 dist（KaTeX 上线）。

**剩余事项**：真实 iPad 设备核对（ST-016，需 owner 执行）；真实试卷 OCR 准确率与中文扫描耗时评估（产品问题）；下一次 R2 备份恢复周期观察。

## 阶段 3 · ST-016 生产栈现场校验（2026-10-29 部分完成）

**结果**：本地生产栈经 caddy:8180（与隧道同路径）实测新功能在线：`/api/guidance/pool-health?subject=math` 返回真实生产数据（math.demo.basic 已发布 5、未见 3、已曝光 2）；`/health/live` 报告 `app_revision=drill-a`；manifest/图标/root 200；公网入口 https://shutong.xmanspace.asia 仍 302 → Cloudflare Access（门禁红线保持）。推送链远端 CI [run 40808468517](https://github.com/xman900719/pageboy/actions/runs/40808468517) 五作业全绿（含 iPad/WebKit 作业与 vitest）。

**范围**：只读核验 + 文档；无代码变更（除 CI 证据补记提交 `6a093eb`）。

**验证证据（实测）**：
- `curl https://shutong.xmanspace.asia/` → 302 → cloudflareaccess 登录页（root/icon/sw 同）。
- 本机生产栈（caddy → api，Bearer 来自 infra/.env）：pool-health、subjects、health/live、manifest、icon-180.png 全部 200 且内容正确。
- 远端 CI：api-and-docs / pg-migration / web-build / web-e2e / web-e2e-webkit 五作业 success。
- 阶段提交链：`c429910`(ST-013) → `0656cb4`(ST-014) → `94316ee`(ST-015) → `34eeccc`(ST-017) → `8d42bf0`(docs) → `6a093eb`(CI 证据)，已全部推送。

**剩余事项（需 owner）**：真机 iPad 核对清单已交付（[docs/operations/ipad-field-checklist.md](../operations/ipad-field-checklist.md)）——11 项检查（基础循环/公式渲染/PWA 与横竖屏/断网文案），等待 owner 执行结果回填后 ST-016 才能标完整。

## 阶段 3c · ST-018 会话续答（2026-10-29 完成，因网络阻塞尚未推送）

**结果**：修复诊断未见题"空烧"缺陷——领取未见题后刷新/重开/切后台，`GET /api/practice/resume`（只读，仅诊断曝光）恢复同一曝光，J9 双引擎验证"同题恢复→判分→完成→无残留"。

**范围**：main.py 只读端点 + DiagnosisView 恢复 + api.ts + 测试 + OpenAPI（+39 行）+ 记录。

**验证证据**：resume 单测 7 passed；全量 API **134 passed / 25 skipped**；chromium **17 passed / 3 skipped**；iPad/WebKit **20 passed**；契约/文档/zensical 全 PASS。

**过程问题（如实）**：首版给训练视图也启用续答 → 练习按钮文案切换导致后续 e2e 用例按文案定位超时（级联失败）；按产品语义收窄为仅诊断曝光，并补 `test_training_exposure_is_not_resumed` 反例。

**剩余事项**：本地提交待推送——GitHub 当前不可达（ssh 443 连接被 198.18.0.1x 拦截关闭，https 亦不通，`git push` 三次重试失败；非仓库权限问题，早前同一 remote 推送成功）。网络恢复后立即推送并核对 CI。

**（同日补齐）**：网络恢复后 `135017b`（J8）与 `198ad7a`（ST-018）已推送，[run 40841552538](https://github.com/xman900719/pageboy/actions/runs/40841552538) 五作业全绿；生产栈已部署 `shutong-api:api-198ad7a`（含 ST-018 续答），smoke 全绿。

## 阶段 3b · J8 扫描件摄取 UI 旅程（2026-10-29 完成）

**结果**：ST-014 的 UI 旅程证据补齐——运行时 Pillow 合成两页图像型 PDF → 审核台上传 → OCR 解析草稿（页码标记+识别文本断言）→ 逐题人工誑写（含公式）→ 确认导入 → 审核 → 发布 → 练习渲染并判分。这正是 owner 的真实导入闭环。

**验证证据**：chromium **16 passed / 3 skipped**（J8 3.8s）；iPad/WebKit **19 passed**；CI 两作业增设本地解析器安装步骤后推送复验（见下一条提交的 CI 运行）。

**剩余事项**：owner 的 iPad 真机核对（清单已交付）；真实中文扫描件 OCR 准确率评估（产品问题）。


## 阶段 4 · 真机 iPad 打通与 ST-016 闭合（2026-10-30）

**结果**：经 USB（信任配对 + Web Inspector + pymobiledevice3）实际驱动 owner 的 iPad 完成全部可自动核对项，ST-016 闭合。同日修复三个生产级网络/运维问题（隧道协议、隧道自愈、iPad 入网）。

**范围**：`docs/quality/st-016-production-onsite.md`（记录）、`infra/tunnel-watchdog.sh`（+crontab）、`infra/compose.local.yaml`（http2）、使用文档（Safari/PWA 存储独立说明）、IMPLEMENTATION_PLAN/PROJECT_STATUS/CODEX_START_HERE 状态滚动。

**验证证据（真机实测，非仿真）**：
- ① 首页三视图 + 题库体检（已发布5/未见3/已曝光2，与生产库一致）
- ② 练习取题→选 B→提交→「本题得分 1/1 · 已审核答案自动比对」
- ③ 阶段诊断→提交→「符合独立验证条件」+「计划已刷新」+「证据不足，无法比较」（无虚构分数）
- ③ ST-018 生产实测：早前网络失败时领取的未见题未被烧掉，自动恢复并正常提交
- ④ 公式渲染：生产库种入标注「虚构测试数据」的公式题；题干 `.katex`×2、错误 0、无字面 `$`；选项 `<b>` 仅作字面文本（转义安全）
- ⑤ PWA：standalone 实测 `navigator.standalone=true`
- ⑦ 记住令牌：PWA 内勾选→localStorage 写入→完整重载→自动进入；owner 复测「重开直接进入」
- ⑧ 断网文案：构建级验证（iPad 加载构建含新文案，旧文案不存在）
- 隧道修复：http2 切换稳定；1033  watchdog crontab 上线（首运行健康空转）

**剩余事项**：owner 目视复核横竖屏/分屏（仿真面 R1-R3 已锁）；iPad 入网持久方案三选一（路由器规则 / Clash allow-lan / 保留临时转发）待 owner 决定；owner 首次真实试卷导入体验待发生；Cloudflare MCP 授权已失效（后续 Access 侧调整需重新授权）。

---

# 长任务最终汇总报告（2026-10-30）

**任务**：自行决定优化与新功能，交付「可在生产环境切实使用」的书童；iPad 测试与调试；自行推送 GitHub 并做版本管理；每阶段产出汇总。

**交付内容（自规划 ST-013~ST-018 + ST-016 现场核验）**：
| 任务 | 内容 | 状态 |
|---|---|---|
| ST-013 | 题干公式渲染（KaTeX `$…$`/`$$…$$`，安全转义）+ 线上文案缺陷修复 | 已完成，CI 绿 |
| ST-014 | 扫描 PDF 自动 OCR 摄取（pdftoppm→tesseract 逐页草稿）+ J8 真实导入闭环 | 已完成，CI 绿 |
| ST-015 | 题库体检（纯函数+端点+首页卡片 J7/J7b） | 已完成，CI 绿 |
| ST-017 | 标签化部署/回滚 + `/health/live` 构建身份 + 本机生产栈演练 | 已完成 |
| ST-018 | 会话续答（诊断未见题刷新不空烧）+ J9 | 已完成，CI 绿 |
| ST-016 | 生产栈现场校验 + 真机 iPad 全链核对 | 已完成（见上） |

**质量证据**：后端 **134 passed / 25 skipped**；chromium e2e **17 passed / 3 skipped**；iPad/WebKit e2e **20 passed**；远端 CI 五作业全绿（含 iPad 作业）；部署演练数据零损伤；备份链路未变。

**版本管理**：13 个提交按 `feat/test/docs` 语义组织并全部推送 `codex/st-003-private-ingestion`；annotated tag **v1.6.1**；生产镜像标签 `shutong-api:api-198ad7a`（回滚目标 drill-a 保留本地）。

**运维修复（本次长任务内发现并处置）**：① 隧道 QUIC→HTTP/2；② 隧道 1033 自愈 watchdog（crontab）；③ iPad→Access 登录域网络通道（临时代理转发，待持久化决策）；④ 线上网络错误文案误报「本地服务」。

**诚实边界**：未做真实试卷导入（OCR 准确率只做了合成中文样本：2 页 1.7s / 8 页 10.5s，正文可读、数学符号不可靠——产品设计即"OCR 只是人工誑写草稿"）；未做真实 iPad 拍照质量评估；横竖屏/分屏为仿真断言+部分目视；效果推断/成绩预测按项目红线不在范围。

**下一阶段建议（需 owner 输入）**：真卷导入试用 → 依据反馈决定「目标蓝图/题池运营工具」是否值得建；iPad 入网持久方案落地；如需 Access 侧调整（会话时长/服务令牌）需重新授权 Cloudflare MCP。
