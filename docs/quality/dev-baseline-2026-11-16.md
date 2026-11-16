# 2026-11-16 开发基准线与验证记录

日期：2026-11-16。范围：PR #8–#13（`pageboy-home` 双环境强隔离、全科 135 候选知识点终审、校考错误分析与管理端中文本地化、k12100 配置迁移）及 `5004aae`（ST-EXAM-AUTOSYNC R1/R2 与多学科分析报告导入整合、6-Tab 管理端、Alembic `0013–0016`、worktree 收口清理）后的新开发基准线。

## 基准线状态与环境隔离

- **代码基线**：基于 `origin/codex/st-001-ci`（`e43e24a`）整合合入特性分支 `feat/school-exam-autosync-report-baseline`（`5004aae` 起），单仓干净无额外 Git Worktree 残留。
- **架构与前后端双入口**：Vue 3 MPA 双入口（学生端 `index.html` / 管理端 `admin.html`）+ FastAPI 模块化单体；管理端「学校考试」保留「全科校考同步」（Tab 5）与「报告导入与核对」（Tab 6）6-Tab 并存。
- **数据库迁移基线**：Alembic 单头 `0016 (head)`（线性链：`0012` → `0013_school_exam_autosync` → `0014_exam_header_r2` → `0015_school_exam_reports` → `0016_school_exam_report_cards`）。
- **开发环境与数据策略**：
  - 开发目录位于 `/media/xc/backup_ext4/pageboy-home/development`（`0700` 权限）；开发库 `shutong-dev.sqlite3` 处于 `0016`，保留 2018–2025 真题与既有真实校考/报告档案（无虚构测试样卷）。
  - 遵循仓库根目录 `AGENTS.md` 第 14 条与 [开发环境测试数据政策](test-data-policy.md)：开发入口统一使用 `scripts/run_dev_env.py`（`127.0.0.1:8000` + `127.0.0.1:5173`，禁用 `4173` 与 `run_manual_test_env.py`），`scripts/seed_demo.py` 未获 Owner 批准与引用环境变量时 fail-closed。
- **冷备份留存**：清理两个旧 worktree 前的全量冷备份保存于 `/media/xc/backup_ext4/code/pageboy-backup/20261116-worktree-cleanup-autosync-r2-report-merge-snapshot/`（含 `SHA256SUMS` 校验）。
- **生产栈边界**：宿主机生产栈仍保持独立运行于 `shutong+` 用户与 `v1.6.1`（`shutong-api:api-198ad7a`），本次开发基线整合未触碰生产配置或生产库。

## 可复现验证命令与本地实测结果

在仓库根目录执行（本地 Python 3.14.4 / Node.js / npm 10.9.3）：

```bash
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
bash scripts/check_env_isolation.sh
cd apps/web && npm run test:unit && npm run build
cd apps/web && npm run test:e2e && npm run test:e2e:ipad
```

| 检查项目 | 实测结果 | 备注 |
|---|---|---|
| `make verify`（后端单测） | **346 passed, 25 skipped** | 25 项为 PostgreSQL 16 并发/迁移集成项（本地开发用户无 `docker` 权限跳过） |
| 契约、文档与 OpenAPI | **全部通过** | JSON Schema 正反例 `PASS`；7 张 Mermaid SVG 重绘；65+ 篇 Markdown 链接 `PASS`；`test_docs_checker.py` `2 passed`；OpenAPI 快照一致 |
| `zensical build --strict` | **通过** | 严格构建零警告/零错误 |
| 前端单测与生产构建 | **通过** | Vitest `26 passed (4 files)`；`vue-tsc -b && vite build` 通过 |
| Chromium E2E (`npm run test:e2e`) | **26 passed, 5 skipped** | 3 项 iPad 专属断言 + 2 项 `EXAM_SYNC_VISUALS=1` 截图用例按设计跳过 |
| iPad WebKit E2E (`npm run test:e2e:ipad`) | **29 passed, 2 skipped** | 含 6-Tab（含「全科校考同步」与「报告导入与核对」）iPad 视口零横向溢出断言 |
| 宿主机 iPadOS 模拟机人工验收 | **全部通过（16 项）** | Owner 于 2026-11-16 确认放行，详见 [st-exam-autosync-r2-manual-test.md](st-exam-autosync-r2-manual-test.md) |
| `scripts/seed_demo.py` fail-closed | **通过** | 未设审批变量时退出码 `1`，拒绝写入虚构数据 |
| `scripts/check_env_isolation.sh` | **全部 PASS** | 无残留运行产物，开发与生产权限硬隔离有效 |

## 未验证与保留边界

- **PostgreSQL 16 迁移往返与并发**：本地开发用户因安全隔离不在 `docker` 组（25 项 PG 测试跳过），由本 PR 触发 GitHub Actions `pg-migration` 作业在真实 PostgreSQL 16 容器中验证 `0001 → 0016 → downgrade 0004 → 0016 → alembic check`。
- **真实外部平台联调**：真实 `k12100` 账号与远程学校卷源采集仍保持 `BLOCKED / NOT_VERIFIED`。
- **生产部署与回滚**：当前 `codex/st-001-ci` 仅代表开发主干基线；生产环境升级须另行经标签化发布与停机/备份确认门禁执行，见 [生产环境运维说明](../operations/production-environment.md) 与 [部署手册](../operations/deployment.md)。
