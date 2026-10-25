# 书童 · ShuTong（Codex 可接手工程包）

> **交接版本：V1.6-foundation / 2026-10-18**  
> **状态：可运行的开发基础骨架，非完整产品，不含真实北京中考真题或个人学校试卷。**

## 从这里开始

1. 先读 [CODEX_START_HERE.md](CODEX_START_HERE.md)，然后遵守根目录 [AGENTS.md](AGENTS.md)。如果使用 Codex Chat，可直接粘贴 [PROMPT_FOR_CODEX.md](PROMPT_FOR_CODEX.md)。
2. 按 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) 任务单逐个实现，不能跳过验收测试。
3. 业务规则权威依据：[docs/design](docs/design)；契约：[contracts](contracts)；验收：[docs/quality/acceptance.md](docs/quality/acceptance.md)。
4. 旧版方案及二次评估仅作溯源：[reference/legacy](reference/legacy)，**不是当前规范**。

## 本地开发（SQLite，无 Docker）

```bash
# Debian/Ubuntu：本地 PDF/图片解析依赖
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
cd services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export SHUTONG_TOKEN='replace-with-a-long-private-token'
python -m alembic upgrade head
uvicorn shutong.main:app --host 127.0.0.1 --port 8000
```

另开终端：

```bash
cd apps/web
npm install
npm run dev
```

打开 `http://localhost:5173` 并输入相同的 `SHUTONG_TOKEN`。**仓库没有预置任何真实试卷**；可以使用后述虚构样例脚本导入测试题。

```bash
export SHUTONG_TOKEN='replace-with-a-long-private-token'
python scripts/seed_demo.py
```

开发时 `api` 的 `DATABASE_URL` 不设置则使用项目运行目录下的 SQLite 文件。**SQLite 仅是本地开发回退方案，生产使用 PostgreSQL。**

## 质量检查

```bash
cd services/api && pytest -q && cd ../..
python scripts/validate_contracts.py
python scripts/check_docs.py
python scripts/check_openapi.py
cd apps/web && npm run build
cd apps/web && npx playwright test   # 用户旅程（自动起临时 API:18765 + preview:4173）
cd apps/web && npm run test:e2e:ipad   # iPad（WebKit 仿真）通道：旅程+可访问性+720–980px 响应式断言
```

其中前端构建需先 `npm install`；旅程首跑需 `npx playwright install chromium`，iPad 通道另需 `npx playwright install webkit` 与 `sudo npx playwright install-deps webkit`（Linux）；宿主 8000 被占用时经 `API_PROXY_TARGET` 覆盖代理目标。完整文档站点还需 `pip install zensical && zensical build --strict`。本地全部门禁（含隔离 PostgreSQL 迁移与真并发）已随 ST-004~008 验证，详见各 [验证记录](docs/quality/acceptance.md)；远端 CI 于 2026-10-23 在 `codex/st-003-private-ingestion` 分支[实际运行通过](https://github.com/xman900719/pageboy/actions/runs/39898363746)（含 pg-migration/web-e2e 护栏）；ST-010 起 CI 另含 web-e2e-webkit（iPad/WebKit 仿真）作业。

## 初始功能 / 暂未完成

**已提供的行为（均见 docs/quality/ 各验证记录）**：私有 Token 鉴权；来源台账与人工审核发布；私有 PDF/PNG/JPEG/音频上传、哈希与导入确认；已发布题修订新版本（历史不可变）；**练习会话与确定性题目轮换；曝光原子化与并发安全**（每逻辑题至多一次未见首曝）；作答幂等（同键重试同结果）；**数学纵向闭环与独立复测可观察对比**（不足即"证据不足"，绝不宣称涨分）；**学校私卷逐题人工确认**（OCR 草稿须人工核对，总分不折算考点证据）；**四科题型**（单选/短答归一化判分/主观自评独立来源）与题组、听力音频；评分来源可追溯列表；三视图学习 UI（首页/练习/阶段诊断，Playwright 用户旅程通过）；学校考试总分录入；科目目标版本；知识点画像与规则计划；基本移动端 Web；PWA 静态缓存（不缓存学生数据）。

**仍待实现/校准**：复杂试卷/公式/图表自动解析、扫描 PDF 自动 OCR、人工审核 UI、富文本公式渲染引擎、完整目标蓝图、真实测试题池管理、完整 PWA 离线体验策略、异地恢复实测（ST-OPS）、对学习效果的校准。不存在真实中考分数预测能力；所有"可观察对比"均为小样本记录，不代表能力或涨分结论。

## 重要安全限制

- 仅用于私有个人验证；代码仓库内不得加入真题原卷、学生个人信息、API 密钥和任何受版权限制的附件。
- 真实运行前在 `infra/.env` 设置强令牌与随机数据库口令；仅通过 VPN/私有网络访问。
- 学校试卷未有题目级核对成绩时，不能生成知识点级能力证据。
- 计划阈值是**未校准的产品启发式**，不可以宣称预测中考分数。


ST-003 原件默认保存在启动目录的 `private-data/attachments`；可用 `SHUTONG_PRIVATE_DIR` 指向受保护的持久目录，禁止放入 Web 静态目录。容器使用 `/var/lib/shutong/attachments` 和 Compose `private_files` 卷。导入 API、限制、迁移与可执行测试见 [ST-003 记录](docs/quality/st-003-private-ingestion.md)。备份脚本仍仅覆盖数据库，首次真实长期使用前须完成 [联合备份和隔离恢复](docs/operations/backup-policy.md)。
