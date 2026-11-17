---
name: verify-and-ci
description: >-
  Use this skill when running backend/frontend tests, validating JSON Schema contracts,
  syncing OpenAPI snapshots, checking Docs-as-Code builds (Zensical), verifying Alembic
  migrations, or performing pre-delivery verification gates in the Pageboy repository.
---

# 书童 (Pageboy) 全栈验证与 CI 门禁标准作业程序

## 1. 核心验证顺序

按 `AGENTS.md` 第 5.1 节要求，始终遵循**「定点正反例测试 → 仓库 `make verify` 基线 → Docs 严格构建 → 环境隔离自检」**的递进验证顺序。

### 1.1 后端、契约、文档与 OpenAPI 一键门禁
在仓库根目录运行：
```bash
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
bash scripts/check_env_isolation.sh
```
- `make verify` 依次执行：
  1. `cd services/api && python -m pytest -q`（普通开发用户不在 `docker` 组，25 项 PostgreSQL 真实并发/容器迁移集成测试预期为 `skipped`，须如实记录，不得伪称全量运行）。
  2. `python scripts/validate_contracts.py`（JSON Schema 正反例校验）。
  3. `node scripts/render_diagrams.mjs` + `python scripts/check_docs.py` + `pytest scripts/test_docs_checker.py -q`（Mermaid 矢量图渲染与 Markdown 本地链接/图片存在性检查）。
  4. `python scripts/check_openapi.py`（实际 FastAPI 路由与 `contracts/openapi.yaml` 一致性比对）。

### 1.2 修改 API 路由或响应模型时的契约同步
任何 FastAPI 路由或 Pydantic Schema 变更后，必须先重新生成 OpenAPI 快照再校验：
```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/generate_openapi.py
PATH="$PWD/.venv/bin:$PATH" python scripts/check_openapi.py
```

### 1.3 修改 `guidance.py` 时的纯度红线
`services/api/shutong/guidance.py` 必须保持纯业务计算（由 `test_guidance_purity` AST 白名单 + 符号扫描 + 子进程隔离锁定），严禁引入 FastAPI/HTTP、SQLAlchemy/DB、OCR 或外部模型 SDK。

### 1.4 数据库迁移（Alembic）验证红线
- 本地迁移冒烟**仅允许针对 `/tmp/` 下的隔离临时 SQLite 库**执行，严禁对未知 `DATABASE_URL` 直接执行升级或降级：
  ```bash
  cd services/api
  DATABASE_URL=sqlite+pysqlite:////tmp/shutong-smoke.sqlite3 ../../.venv/bin/python -m alembic upgrade head
  rm -f /tmp/shutong-smoke.sqlite3
  ```
- 真实 PostgreSQL 16 全新库往返（`0001 -> head -> downgrade 0004 -> head -> alembic check`）在本地无 `docker` 权限时由 GitHub Actions `pg-migration` 作业（`.github/workflows/verify.yml`）验证。

### 1.5 前端单元、构建与双引擎 E2E 门禁
```bash
cd apps/web && npm run test:unit && npm run build
cd apps/web && npm run test:e2e
cd apps/web && npm run test:e2e:ipad
```
- `npm run test:e2e`（Chromium）与 `npm run test:e2e:ipad`（WebKit / `iPad (gen 7)` 810×1080 视口）自管临时 SQLite 与双 webServer（`18765` / `5173`）；若宿主机 `5173` 已启动开发服务，运行 E2E 前可先检查 `uv run python scripts/run_dev_env.py status` 避免端口争用。
