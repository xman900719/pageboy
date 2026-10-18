# ST-001 本地基线验证记录

日期：2026-10-18。范围：交接包本地开发基线；不代表完整 MVP、远端 CI 或运行灾备验收完成。用户确认暂保留远端 CI 未验证。

## 环境与初始状态

- 接手目录没有 `.git`，已按启动页初始化本地仓库；无远端推送。
- Python 3.14.4、Node 22.19.0、npm 10.9.3；CI 配置 Python 3.12，尚未在该环境执行。
- `.agent/policies/` 与用户引用的 `/home/xc/.codex/RTK.md` 均不存在；已读取根目录契约和当前设计/验收文档。
- 后端未改动时：API/业务测试 8 passed，文档检查器 2 passed；Schema 正反例、链接和 OpenAPI 检查通过。
- Web 初始 `npm run build` 失败：`src/main.tsx(5,49): TS2339: Property 'env' does not exist on type 'ImportMeta'`。
- 文档初始 `zensical build --strict` 失败：`product/milestones.md` 链接到站点之外的根目录实施计划，报告 `page does not exist`。

## 修复及不变项

- 增加 `apps/web/src/vite-env.d.ts`，加载 Vite 客户端类型；新增 npm 锁文件，CI 使用 `npm ci`。
- 将文档站点无法提供的根目录计划/契约链接改为明确的仓库路径引用；不复制契约、不关闭严格构建。
- Git 忽略 Python 包元数据、TypeScript 构建信息、文档产物及缓存。
- 没有修改业务 API、ORM、判分或 `guidance.py`；OpenAPI 快照保持一致。不导入真实学生数据或试卷。

## 可复现命令与结果

从仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e './services/api[test]' -r requirements-tools.txt
.venv/bin/python -m pip install zensical
export PATH="$PWD/.venv/bin:$PATH"
make verify
cd apps/web
npm ci --no-audit --no-fund
npm run build
cd ../..
zensical build --strict
```

已实际执行：依赖安装通过；`make verify` 包含 8 项 API/业务测试、2 项文档检查器测试、Schema 合法样例/非法年份类型、URL、SHA 等反例、Markdown 本地资源及 OpenAPI 比较，全部通过。前端构建通过（Vite 6.4.4，29 modules）；Zensical 0.0.71 严格构建通过。

迁移在自动清理的临时目录内执行，未操作用户数据库；以下为等效可复现命令（实际执行使用同样的临时目录和子进程环境隔离）：

```bash
python - <<'PY'
import os, subprocess, sys, tempfile
with tempfile.TemporaryDirectory(prefix='pageboy-baseline-') as directory:
    env = dict(os.environ, DATABASE_URL=f'sqlite+pysqlite:///{directory}/baseline.sqlite3')
    for command in ('upgrade', 'current'):
        args = [sys.executable, '-m', 'alembic', command]
        if command == 'upgrade':
            args.append('head')
        subprocess.run(args, cwd='services/api', env=env, check=True)
PY
```

结果：两个子进程均退出 0，`alembic current` 输出 `0001 (head)`。原始调用采用含 `../..` 的解释器路径，Python 发出 `sys.prefix` 路径警告；迁移未失败。

已用 PyYAML BaseLoader 静态验证 Workflow 同时包含 `push`/`pull_request` 且无路径或分支过滤，故配置未排除 `AGENTS.md`；此检查不能证明 GitHub 实际触发。

## 未验证、兼容与回滚

- AC-DOC-03 远端触发、GitHub Actions 执行、PostgreSQL、部署与恢复演练未验证；ST-001 不标记全部完成。
- API 测试存在一条 Starlette 对 httpx TestClient 的弃用警告；本次没有为消除警告替换测试框架。
- 不涉及业务数据迁移或 API 变更；修复可按 Git 文件差异回退，缓存可重新生成，无需数据库回滚。
- `MANIFEST.sha256` 保留交接包原始清单，用于追溯输入；它不是后续 Git 工作树的实时校验清单。
- 下一项开发任务：ST-002；附件导入、并发曝光和长期真实数据恢复门禁仍未完成。
