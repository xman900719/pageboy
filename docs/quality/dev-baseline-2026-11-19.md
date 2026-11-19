# 2026-11-19 开发基准线与验证记录

日期：2026-11-19。范围：在 [2026-11-16 开发基准线](dev-baseline-2026-11-16.md)（Alembic `0016`）之后，合并 PR #15–#23 至 `main`（`914afb1`）后的最新全栈开发基准线。

## 基准线变更范围（PR #15–#23）

- **插件与治理对齐（PR #15）**：`pageboy-dev` / `pageboy-ops` 工作区插件配置及 `AGENTS.md` 对齐。
- **管理端与校考工作台演进（PR #16–#19）**：管理端分阶段单卡 step-gate 流程、三列台账与学科隔离及全量中文本地化；`k12100` 报告同步、去重、排名与 SSoT 不变量；主题 10–13 校考待核对工作台、三层知识点自动关联、学生错题复盘与阶段重组（Alembic `0017–0019`）。
- **练习双工作台与错因诊断（PR #20）**：学生端练习页方案 A 错题回顾与纯书童对话引导、管理端错因 AI 诊断三选一与改进对策闭环（Alembic `0020_tutor_error_diagnosis`）。
- **校考复盘闭环（PR #21 / ST-021~ST-023）**：学生端「校考复盘」三步引导与去惩罚化反馈、失分题题干与作答防重复抽取及家长确认入库（Alembic `0021_school_item_stem`）、「书童陪你想」苏格拉底对话复盘与管理端只读折叠回溯（Alembic `0022_school_reflection_coach`）。
- **知识点图谱与双游戏（PR #22–#23）**：知识合成工坊 & 迷雾科技树探险双游戏及管理端启停/护盾/重置联动；学生端知识点关系图谱升级为交互式 Vue Flow + Dagre 有向图。

## 基准线状态与环境隔离

- **代码基线**：`main` 分支 `914afb1`（Merge PR #23），单仓干净无额外 Git Worktree 残留。
- **数据库迁移基线**：Alembic 单头 `0022 (head)`（自 `0016` 起线性链：`0016_school_exam_report_cards` → `0017_school_exam_report_platform` → `0018_report_ranks_highest_and_dedup` → `0019_canonical_report_and_attachment_uniqueness` → `0020_tutor_error_diagnosis` → `0021_school_item_stem` → `0022_school_reflection_coach`）。
- **开发环境与数据策略**：
  - 开发目录位于 `/media/xc/backup_ext4/pageboy-home/development`（`0700` 权限）；开发库 `shutong-dev.sqlite3` 处于 `0022`，校考不变量体检通过（报告 2 份 / 档案 10 场 / 附件 33 份 / 异常 0 项），无虚构测试样卷。
  - 遵循仓库根目录 `AGENTS.md` 第 14 条与 [开发环境测试数据政策](test-data-policy.md)：开发服务统一通过 `scripts/run_dev_env.py`（`127.0.0.1:8000` + `127.0.0.1:5173`，禁用 `4173`）运行，`scripts/seed_demo.py` 默认 fail-closed。
- **生产栈现状与差异边界**：宿主机生产栈当前运行 `app_revision=api-b5bdc98`（`env=prod`，经 `http://127.0.0.1:8180/health/live` 实测），对应 2026-11-14 提交 `b5bdc98`（Alembic `0010`），与当前开发基线相差 **12 个 Alembic 迁移（`0011–0022`）** 与 39 个代码提交。本次开发基线建立未触碰生产配置、生产库或生产容器。

## 可复现验证命令与本地实测结果

在仓库根目录执行（本地 Python 3.14.4 / Node.js v22.19.0 / npm 10.9.3；因 `127.0.0.1:5173` 正在运行开发服务，Playwright E2E 通过 `E2E_WEB_PORT=5174` 隔离端口执行）：

```bash
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
bash scripts/check_env_isolation.sh
cd services/api && DATABASE_URL=sqlite+pysqlite:////tmp/shutong-smoke.sqlite3 ../../.venv/bin/python -m alembic upgrade head && rm -f /tmp/shutong-smoke.sqlite3
cd apps/web && npm run test:unit && npm run build
cd apps/web && E2E_WEB_PORT=5174 npm run test:e2e && E2E_WEB_PORT=5174 npm run test:e2e:ipad
```

| 检查项目 | 实测结果 | 备注 |
|---|---|---|
| `make verify`（后端单测） | **376 passed, 25 skipped** | 25 项为 PostgreSQL 16 并发/迁移集成项（开发用户 `xc` 不在 `docker` 组按设计跳过） |
| 契约、文档与 OpenAPI | **全部通过** | JSON Schema 正反例 `PASS`；7 张 Mermaid SVG 重绘；78 篇 Markdown 链接 `PASS`；`test_docs_checker.py` `2 passed`；OpenAPI 快照一致 |
| `zensical build --strict` | **通过** | 严格构建零警告/零错误（0.33s） |
| 隔离 SQLite Alembic 迁移 | **通过** | `/tmp/shutong-smoke.sqlite3` 从空库 `upgrade head` 至 `0022` 成功 |
| 前端单测与生产构建 | **通过** | Vitest `47 passed (8 files)`；`vue-tsc -b && vite build` 通过（2.03s） |
| Chromium E2E (`npm run test:e2e`) | **30 passed, 5 skipped** | 3 项 iPad 专属 R1–R3 + 2 项 `EXAM_SYNC_VISUALS=1` 截图用例按设计跳过 |
| iPad WebKit E2E (`npm run test:e2e:ipad`) | **33 passed, 2 skipped** | 2 项 `EXAM_SYNC_VISUALS=1` 截图用例按设计跳过；含 a11y、Vue Flow 图谱、双游戏、ST-021~023 全绿 |
| 宿主机 iPadOS 模拟机人工验收 | **全部通过（主题 1–8、10–19）** | 见 [manual-acceptance.md](manual-acceptance.md)，主题 8 & 10–19 已于 2026-11-18~19 确认放行 |
| `scripts/check_env_isolation.sh` | **全部 PASS** | 无残留运行产物，开发与生产权限硬隔离有效 |

## 未验证与保留边界

- **PostgreSQL 16 迁移往返与并发**：本地开发用户因安全隔离不在 `docker` 组（25 项 PG 测试本地跳过），须确认 GitHub Actions `pg-migration` 作业在真实 PostgreSQL 16 容器中完成 `0001 → 0022 → downgrade 0004 → 0022 → alembic check` 验证。
- **生产发布前提**：生产环境从 `api-b5bdc98`（`0010`）升级至 `0022` 跨越 12 个数据库迁移，且 `infra/rollback.sh` 不支持 Schema 降级回滚；发布前必须由 Owner 启用 `pageboy-ops` 插件（激活 `ops-backup-deploy`）、显式授权 R3/R4 生产操作、先执行完整 R2 联合备份（`backup.sh`），并在 `shutong-prod` 账户下按 [生产环境运维指南](../operations/production-environment.md) 执行单向发布与 `python -m shutong.taxonomy_audit` 核验。
