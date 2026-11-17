---
name: frontend-ipad-acceptance
description: >-
  Use this skill whenever modifying files under apps/web/ (Vue 3 student index.html or
  admin.html views, components, CSS styles, or E2E specs), starting local dev servers,
  or preparing iPadOS simulator manual acceptance checklists for the Owner.
---

# 前端开发、iPadOS 模拟机调试与选项式人工测试门禁 SOP

> 权威依据：`AGENTS.md` 第 9.1.13 条与 [docs/quality/manual-acceptance.md](../../../../docs/quality/manual-acceptance.md)。

## 1. 硬性网络与入口红线

1. **统一开发入口**：只允许使用 `scripts/run_dev_env.py` 管理本地开发前后端服务（后端 `127.0.0.1:8000` + 前端 Vite dev `127.0.0.1:5173`）。
2. **严禁非回环监听與废弃端口**：严禁监听 `0.0.0.0` 或局域网 IP；端口 `4173` 与旧脚本 `run_manual_test_env.py` 已永久废弃。
3. **测试数据 fail-closed**：`run_dev_env.py start` 默认只挂载 `$PAGEBOY_HOME/development` 下的开发库，绝不自动灌入虚构测试数据。

## 2. 标准执行步骤

### 步骤 1：宿主机自动化门禁先行
在交付人工测试前，必须在宿主机通过前端单测、构建与双引擎 E2E（含 `axe-core` 无障碍与 `R1–R3` 720–980px 零横向溢出断言）：
```bash
cd apps/web && npm run test:unit && npm run build
cd apps/web && npm run test:e2e && npm run test:e2e:ipad
```

### 步骤 2：启动回环开发服务并完成连通性探针自检
```bash
# 启动 127.0.0.1:8000 与 127.0.0.1:5173
uv run python scripts/run_dev_env.py start

# 验证服务健康与回环绑定
uv run python scripts/run_dev_env.py status
```

### 步骤 3：向 Owner 提供模拟机入口与选项式人工核验报告
1. **模拟机调出命令**：
   - 竖屏（`810 × 1080`）：`uv run python scripts/run_dev_env.py sim`
   - 横屏（`1080 × 810`）：`uv run python scripts/run_dev_env.py sim-landscape`
   - 浏览器访问入口：学生端 `http://127.0.0.1:5173/`，管理端 `http://127.0.0.1:5173/admin.html`
2. **选项式人工测试清单**：
   - 在 `docs/quality/checklists/`（或对应阶段核验文档）中提供带 `- [ ]` 复选框的逐项核验点与四大判定选项（通过 / 不通过 / 暂时中断先修 Bug / 前置阻塞未启动）。
   - **提交红线**：在每个人工测试点未全部获得测试人（Owner）确认勾选 `[x]` 通过前，**绝对禁止执行 `git commit`**（插件 `PreToolUse` Hook 会对未勾完的清单直接 `deny`，并在勾完后弹出 `force_ask` 交由 Owner 最终确认）。
