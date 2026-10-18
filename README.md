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
```

其中前端构建需先 `npm install`；完整文档站点还需 `pip install zensical && zensical build --strict`。本地 Zensical 严格构建与 Web 构建已验证，详见 [ST-001 验证记录](docs/quality/st-001-baseline.md)；远端 CI 与真实恢复演练仍未验证。

## 初始功能 / 暂未完成

**已经提供的基础行为**：私有 Token 鉴权；来源登记；人工审核后发布选择题；版本引用；曝光记录；客观题判分；幂等作答；学校考试总分录入；科目目标版本；知识点表现和简单规则计划；基本移动端 Web；PWA 静态缓存。

**仍需 Codex 按计划实现**：完整试卷导入和图文解析、附件私有存储与上传、人工审核 UI、已发布试题新版本流程、稳定题目轮换、题组与解答题评分、学校卷题目级确认、完整目标蓝图、真实测试题池管理、离线体验策略、异地恢复实测、四科全覆盖、对学习效果的校准。不存在真实中考分数预测能力。

## 重要安全限制

- 仅用于私有个人验证；代码仓库内不得加入真题原卷、学生个人信息、API 密钥和任何受版权限制的附件。
- 真实运行前在 `infra/.env` 设置强令牌与随机数据库口令；仅通过 VPN/私有网络访问。
- 学校试卷未有题目级核对成绩时，不能生成知识点级能力证据。
- 计划阈值是**未校准的产品启发式**，不可以宣称预测中考分数。
