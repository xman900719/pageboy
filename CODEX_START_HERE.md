# Codex 启动页

## 你的首要目标

**从本交接包实现「书童」的可靠、可持续开发 MVP**。不得因为存在总体设计文件而默认业务功能已经编码。先修基线、再纵切、后扩展四科。

## 当前接手点

ST-001~ST-018 已全部完成（本地 + 远端五作业 CI 全绿），AC-OPS-01/02（Cloudflare R2 异地加密联合备份、隔离恢复与 healthchecks.io 静默告警）已实测达成；生产栈运行 `shutong-api:api-198ad7a`（对应标签 `v1.6.1`）。自规划长任务的阶段汇总见 [阶段日志](docs/handoff/stage-reports.md)，日常操作见 [日常使用指南](docs/product/daily-usage.md)。当前处于待 owner 导入首套真实试卷的就绪态。远端默认主干为 `codex/st-001-ci`，与开发分支 `codex/st-003-private-ingestion` 保持同步。历史交接背景见 [工程 handoff](docs/handoff/st-004-and-remaining.md) 与 [执行 prompt](PROMPT_FOR_CODEX.md)。

## 启动检查（顺序执行）

1. `git status --short`，确认工作树干净；如为新解压文件夹，先 `git init`，建立首次提交，但**不自动推送**任何远端。
2. 阅读 `AGENTS.md`、`docs/engineering/development-environment.md`、`docs/operations/production-environment.md`、`docs/product/overview.md`、`docs/design/architecture.md`、`docs/design/data-model.md`、`docs/quality/acceptance.md`。
3. 安装当前 API/测试依赖后，从根目录执行 `PATH="$PWD/.venv/bin:$PATH" make verify`；迁移仅在明确隔离的临时库验证，禁止对未知 `DATABASE_URL` 直接执行升级。
4. `python scripts/validate_contracts.py && python scripts/check_docs.py && python scripts/check_openapi.py`。
5. `cd apps/web && npm ci && npm run build`；如果网络不可用，记录“未执行”，不要编造通过。
6. 理解 P0 风险与已有验收证据，按 `IMPLEMENTATION_PLAN.md` 从下一项未完成任务继续（开发计划已完成，剩余 ST-OPS-01/02 受外部授权门禁约束）；所有“完成”需对应实际测试证据。

## 任务顺序（当前状态见实施计划）

- **ST-001**：校验基线与修复发现的问题，生成可审阅的首次提交。
- **ST-002**：将已发布题的修订升级为不可变新版本，并补充反例。
- **ST-003**：实现安全的原卷和附件导入，加入元数据/哈希/人工审核门禁。
- **ST-004**：把练习中的题目轮换与评价池隔离做可靠（原子曝光、防重复）——已完成本地验收，见 [验证记录](docs/quality/st-004-practice-session.md)。
- **ST-005**：实现数学的证据—差距—计划—独立复测纵向用例——已完成本地验收，见 [验证记录](docs/quality/st-005-math-loop.md)。
- **ST-006**：学校私卷逐题人工核对与附件隔离——已完成本地验收，见 [验证记录](docs/quality/st-006-school-papers.md)。
- **ST-007**：四科题型、公式/图表/阅读/音频/主观自评——已完成本地验收，见 [验证记录](docs/quality/st-007-question-kinds.md)。
- **ST-008**：精简学习首页、复练、阶段诊断、缺证据解释——已完成本地验收（Playwright J1–J4），见 [验证记录](docs/quality/st-008-user-journeys.md)。
- **ST-009**：Docs as Code、UX/可访问性、契约与 CI 收口——已完成验收，见 [验证记录](docs/quality/st-009-closure.md)。
- **ST-010**：iPad（WebKit 仿真）e2e 通道与响应式断言——已完成验收，见 [验证记录](docs/quality/st-010-ipad-emulation.md)。
- **ST-011**：人工审核 UI（审核台）与草稿只读端点——已完成验收，见 [验证记录](docs/quality/st-011-admin-review-ui.md)。
- **ST-012**：iPad PWA 应用化与选配本机记住令牌——已完成验收，见 [验证记录](docs/quality/st-012-pwa-remembered-token.md)。
- **ST-013**：题干富文本与 KaTeX 公式安全渲染——已完成验收，见 [验证记录](docs/quality/st-013-formula-rendering.md)。
- **ST-014**：扫描 PDF 自动 OCR 摄取（pdftoppm→tesseract）——已完成验收，见 [验证记录](docs/quality/st-014-scanned-pdf-ocr.md)。
- **ST-015**：题库体检（纯函数 + 只读端点 + 首页卡片）——已完成验收，见 [验证记录](docs/quality/st-015-pool-health.md)。
- **ST-016**：生产栈现场校验与真机 iPad 全链核对——已完成验收，见 [验证记录](docs/quality/st-016-production-onsite.md)。
- **ST-017（ST-OPS-02 更新回滚）**：标签化部署/回滚脚本与本机生产栈演练——已完成验收，见 [演练记录](docs/quality/st-017-deploy-rollback-drill.md)。
- **ST-018**：诊断未见题会话续答（刷新/重开恢复未作答曝光）——已完成验收，见 [验证记录](docs/quality/st-018-session-resume.md)。
- **ST-OPS-01 / AC-OPS-01~02**：Cloudflare R2 异地联合备份、独立隔离恢复与 healthchecks.io 静默告警——已实测达成，见 [演练记录](docs/quality/st-ops-01-offsite-restore.md)。

## 面向用户的交付格式

```
结果：任务 ID、变更摘要、提交 SHA、完成与未完成
范围：修改文件、契约/文档同步、兼容与回滚边界
验证证据：实际命令、正反例结果、通过/失败/未验证
剩余事项：遗留风险、阻塞条件、下一任务 ID
```

## 重要边界

本包的业务示例全部为合成题，不等同于历年北京中考真题。学校考试当前仅支持**手工总分**；不能将此功能描述为已完成拍照识别。PWA 当前仅静态离线壳，不表示离线练习完整可用。部署/备份脚本为待现场验证的操作模板，尚未达成实测 RPO/RTO。
