# 书童 · ShuTong（Codex 可接手工程包）

> **交接版本：V1.6-foundation / 2026-10-18**  
> **状态：可运行的开发基础骨架，非完整产品，不含真实北京中考真题或个人学校试卷。**

## 从这里开始

1. 先读 [CODEX_START_HERE.md](CODEX_START_HERE.md)，然后遵守根目录 [AGENTS.md](AGENTS.md)。如果使用 Codex Chat，可直接粘贴 [PROMPT_FOR_CODEX.md](PROMPT_FOR_CODEX.md)。
2. 按 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) 任务单逐个实现，不能跳过验收测试。
3. 业务规则权威依据：[docs/design](docs/design)；契约：[contracts](contracts)；验收：[docs/quality/acceptance.md](docs/quality/acceptance.md)。
4. 环境汇总指引：开发规范见 [docs/engineering/development-environment.md](docs/engineering/development-environment.md)；生产运维见 [docs/operations/production-environment.md](docs/operations/production-environment.md)。
5. 旧版方案及二次评估仅作溯源：[reference/legacy](reference/legacy)，**不是当前规范**。

## 本地开发（SQLite，无 Docker）

> 完整开发规范、系统依赖、Vue 3 MPA 双入口及 iPadOS 模拟机验收硬门禁详见 [开发环境汇总与指南](docs/engineering/development-environment.md)。

```bash
# Debian/Ubuntu：本地 PDF/图片解析依赖
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng

# Python 虚拟环境与依赖初始化 (强制使用 uv)
uv venv .venv
source .venv/bin/activate
uv pip install -e "services/api[test]"

# 数据库迁移与本地服务启动 (必须监听 127.0.0.1 回环地址)
export SHUTONG_TOKEN='replace-with-a-long-private-token'
uv run alembic -c services/api/alembic.ini upgrade head
uv run uvicorn shutong.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```bash
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 `http://127.0.0.1:5173`（学生端）或 `http://127.0.0.1:5173/admin.html`（审核端）并输入对应的学生/管理令牌（使用 `scripts/run_dev_env.py start` 启动时，Vite dev 会自动从已隔离配置加载开发令牌）。**仓库没有预置任何真实试卷**；开发环境默认保持空库或既有真实档案，如需在开发库写入虚构测试题，须经 Owner 明确批准并设置审批变量（未批准时 fail-closed，详见 [开发环境测试数据政策](docs/quality/test-data-policy.md)）：

```bash
export SHUTONG_TOKEN='replace-with-a-long-private-token'
PAGEBOY_OWNER_TEST_DATA_APPROVED=1 PAGEBOY_OWNER_APPROVAL_REF='<owner-ref>' uv run python scripts/seed_demo.py
```

开发时 `api` 的 `DATABASE_URL` 不设置则使用项目运行目录下的 SQLite 文件。**SQLite 仅是本地开发回退方案，生产使用 PostgreSQL。**

## 质量检查

```bash
uv run pytest -q services/api
uv run python scripts/validate_contracts.py
make docs   # 自动编译 Mermaid 图表并校验 Markdown 资产
uv run python scripts/check_openapi.py
cd apps/web && npm run test:unit
cd apps/web && npm run build
cd apps/web && npx playwright test   # 用户旅程（自动起临时 API:18765 + dev:5173）
cd apps/web && npm run test:e2e:ipad   # iPad（WebKit 仿真）通道：旅程+可访问性+720–980px 响应式断言
```

> **文档图表维护**：后续新增或修改 Mermaid 图表时，仅需在 `docs/assets/diagrams/*.mmd` 中调整源文件，执行 `make docs` 即可全自动同步重绘 SVG。

其中前端构建需先 `npm install`；旅程首跑需 `npx playwright install chromium`，iPad 通道另需 `npx playwright install webkit` 与 `sudo npx playwright install-deps webkit`（Linux）；宿主 8000 被占用时经 `API_PROXY_TARGET` 覆盖代理目标。完整文档站点还需 `pip install zensical && zensical build --strict`。本地全部门禁（含隔离 PostgreSQL 迁移与真并发）已随 ST-004~008 验证，详见各 [验证记录](docs/quality/acceptance.md)；远端 CI 于 2026-10-23 在 `codex/st-003-private-ingestion` 分支[实际运行通过](https://github.com/xman900719/pageboy/actions/runs/39898363746)（含 pg-migration/web-e2e 护栏）；ST-010 起 CI 另含 web-e2e-webkit（iPad/WebKit 仿真）作业，[run 40178219352](https://github.com/xman900719/pageboy/actions/runs/40178219352) 五作业全绿。

## 初始功能 / 暂未完成

**已提供的行为（均见 docs/quality/ 各验证记录）**：私有 Token 鉴权；来源台账与人工审核发布；**人工审核 UI（审核台：题源登记→来源审核→附件上传解析→逐题确认导入→草稿审核发布，Playwright J5 双引擎通过）**；私有 PDF/PNG/JPEG/音频上传、哈希与导入确认；已发布题修订新版本（历史不可变）；**练习会话与确定性题目轮换；曝光原子化与并发安全**（每逻辑题至多一次未见首曝）；作答幂等（同键重试同结果）；**数学纵向闭环与独立复测可观察对比**（不足即"证据不足"，绝不宣称涨分）；**学校私卷逐题人工确认**（OCR 草稿须人工核对，总分不折算考点证据）；**四科题型**（单选/短答归一化判分/主观自评独立来源）与题组、听力音频；评分来源可追溯列表；三视图学习 UI（首页/练习/阶段诊断，Playwright 用户旅程通过）；学校考试总分录入；科目目标版本；知识点画像与规则计划；**题干公式渲染**（`$…$`/`$$…$$` LaTeX，KaTeX 安全渲染，ST-013）；**扫描 PDF 自动 OCR 摄取**（无文本层 PDF 逐页 OCR 草稿，仍须人工确认，ST-014）；**题库体检**（按知识点的已发布/未见/已曝光计数与诊断余量，ST-015）；**标签化部署/回滚**（`infra/deploy.sh` / `infra/rollback.sh`，ST-017）；基本移动端 Web；PWA 静态缓存（不缓存学生数据）；令牌可选本机记住（默认仅页面内存）。

**仍待实现/校准**：复杂试卷/公式/图表自动结构化、混合版式 PDF 的部分 OCR、OCR 准确率评估、完整目标蓝图、真实测试题池管理、完整 PWA 离线体验策略、异地恢复实测（ST-OPS）、对学习效果的校准。不存在真实中考分数预测能力；所有"可观察对比"均为小样本记录，不代表能力或涨分结论。

## 重要安全限制

- 仅用于私有个人验证；代码仓库内不得加入真题原卷、学生个人信息、API 密钥和任何受版权限制的附件。
- 真实运行前在 `infra/.env` 设置强令牌与随机数据库口令；仅通过 VPN/私有网络访问。
- 学校试卷未有题目级核对成绩时，不能生成知识点级能力证据。
- 计划阈值是**未校准的产品启发式**，不可以宣称预测中考分数。


ST-003 原件默认保存在启动目录的 `private-data/attachments`；可用 `SHUTONG_PRIVATE_DIR` 指向受保护的持久目录，禁止放入 Web 静态目录。容器使用 `/var/lib/shutong/attachments` 和 Compose `private_files` 卷。导入 API、限制、迁移与可执行测试见 [ST-003 记录](docs/quality/st-003-private-ingestion.md)。备份脚本仍仅覆盖数据库，首次真实长期使用前须完成 [联合备份和隔离恢复](docs/operations/backup-policy.md)。
