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

