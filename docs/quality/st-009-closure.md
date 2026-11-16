# ST-009 验证记录：Docs as Code、可访问性与契约/CI 收口

日期：2026-10-22。分支 `codex/st-003-private-ingestion`（仅本地提交，未推送）。验收口径：IMPLEMENTATION_PLAN ST-009 行（全部链接/契约/CI 检查通过）。ST-004~008 期间文档/契约已随做随同步，本项为总核对、新增护栏与可访问性审计。

## 本项工作

1. **文档核对与同步**：README 功能/待办清单重写（剔除已完成项：轮换、题组评分、学校卷逐题确认；补齐 ST-004~008 交付与 Playwright 用法）；`docs/product/overview.md` 审计确认仍准确不动；30 篇 Markdown 链接/图片检查通过；`zensical build --strict` 通过。
2. **契约**：`contracts/openapi.yaml` 与实际 API 三次增量再生成并全部校验一致（ST-005 validation、ST-006 school-exams 子路径、ST-007 practice 子路径）；`check_openapi` 全程绿。
3. **CI 新增护栏**（`.github/workflows/verify.yml`，YAML 校验通过；**远端未运行，不标通过**）：
   - `pg-migration` 作业：全新 PostgreSQL 16 服务上 `upgrade head → check → downgrade 0004 → upgrade head → check`——正是 ST-007 捕获的"内联 FK 指向非基础表使全新 PG 库 0001 失败"缺陷类的永久护栏（SQLite 容忍悬空 REFERENCES 无法拦截）；作业命令与本地 docker PG 16.15 验证逐字一致。
   - `web-e2e` 作业：chromium 用户旅程（命令与本地全绿运行一致）。
4. **可访问性审计与修复**：新增 `@axe-core/playwright` + `e2e/a11y.spec.ts`（三视图 WCAG 2.0/2.1 A/AA 扫描；动画静息后判定；critical/serious 才失败；扫描前状态经种子安全设计，旅程断言不受影响）。首轮发现 31 个 color-contrast serious 节点（结构类规则零违规），三根因路由回 designer 会话修复——`--ink-3 #7c8aa0→#5b6b80`（3.49→5.44:1）、`.badge code` 去 opacity 0.6（2.55→5.67:1）、`--teal #2c7a99→#266e8b`（4.31→5.09:1），仅改 `style.css` 8 行颜色值（布局/字号/动效/文案零变更）；修复后三视图 0 serious/critical。toast 关闭钮"×"与 aria-label「关闭提示」的不一致判定为 incomplete 人工项保留（可访问名称信息量更高；如需严格 2.5.3 再议）。
5. **跨任务并发回归（隔离 PostgreSQL 16.15 容器，均用后清理）**：
   - ST-002 修订并发：`scripts/test_revision_concurrency.py` → **6/6 通过**（models 经 0003~0005 后历史不可变约束完好）。
   - ST-004 练习并发：随 ST-007 验证重跑 EXIT 0（迁移腿 + 19/19）。

## 终验全门禁（2026-10-22，orchestrator 复跑）

- `cd apps/web && npm run build` → 绿（tsc -b 严格 + vite）。
- `npx playwright test` → **7/7**（a11y 三视图零 serious + J1–J4 旅程）。
- 后端 `pytest -q` → 110 passed, 25 skipped, 0 failed。
- `make verify` → contracts/30 Markdown/docs 检查器/OpenAPI 全 PASS；`zensical build --strict` 无问题；`git diff --check` 干净。

## 限制与未验证（如实）

- **远端 CI 首次验证（2026-10-23 补记）**：用户授权推送 `codex/st-003-private-ingestion` 后经三轮运行稳定——前两轮 `web-e2e` 失败（①webServer 写死本地 venv 路径与 /tmp/opencode 目录不存在 → 参数化 PY_CMD/E2E_TMP_DIR；②前端服务启动方式不匹配（当时未构建产物）→ 修正 harness；现统一 Vite dev:5173），第三轮 **[run 39898363746](https://github.com/xman900719/pageboy/actions/runs/39898363746) 四作业全绿**（api-and-docs 1m6s、pg-migration 40s、web-build 15s、web-e2e 1m24s；含 110 项 API 测试、契约/文档/OpenAPI、zensical 严格构建、全新 PG 迁移往返、Playwright 7/7）。既有 Node 20 弃用告警仍在（非失败，未顺手升级）。
- a11y 为 axe 自动扫描（chromium、静息态）：径向渐变页底/半透明 toast 由人工复核（tagline 4.80、footer 4.98、toast 文本 11.21 全部 ≥4.5:1）；未做多浏览器/屏幕阅读器实测。
- ST-OPS-01/02（AC-OPS-01/02）仍为**未演练**：需要 VPS/备份仓库/监控等外部环境与明确授权，本地无阻塞项可推进，按契约如实记录边界，不假造完成。

## 收口状态

开发计划 ST-001~ST-009 全部本地验收完成；2026-10-23 经用户授权推送后，远端 CI（含 pg-migration/web-e2e 新护栏）[实际运行通过](https://github.com/xman900719/pageboy/actions/runs/39898363746)。剩余任务为 ST-OPS-01（首次真实长期数据落库前必须完成异地联合备份与隔离恢复演练——本地机械闭环已具备，异地部分需外部环境与授权）与 ST-OPS-02（运行环境就绪后），均受外部授权门禁约束。
