# ST-015 验证记录：题库体检（`GET /api/guidance/pool-health` + 首页「题库体检」卡片）

日期：2026-10-29。分支 `codex/st-003-private-ingestion`（提交时由 orchestrator 统一落库）。验收口径：IMPLEMENTATION_PLAN ST-015 行——空池/单题/充足三态正反例 + 端点契约与 OpenAPI 再生成校验；UI 只如实呈现后端计数。

## 实现（最小范围）

- **`services/api/shutong/guidance.py`**：新增纯函数 `pool_health(entries)`。输入为 `[{question_id, knowledge_id, seen}]`（一题多知识点各计一行）；题目总数按 `question_id` 去重（修订新版本不重复计数——ST-002 语义保持），知识点行按行计数；输出 `knowledge[]`（published / unseen_for_evaluation / exposed）+ `questions_published` / `questions_unseen_for_evaluation` / `evaluation_available` + 固定免责声明。guidance.py 仍为零 IO 纯模块（AST 白名单测试不涉新增导入）。
- **`services/api/shutong/main.py`**：只读端点 `GET /api/guidance/pool-health?subject=`。查询形状刻意与 `next_item` 一致（最新发布版子查询 + owner 曝光计数），不引入第二套选题口径；曝光计数查询渲染同一 `GROUP BY exposures.question_id` token（本端点不经并发钩子路径，`test_practice_concurrency.py` 钩子仅在隔离 PG 并发脚本内激活、且只驱动 `/api/practice/next`，无交集）。
- **前端**：`api.ts` 增 `PoolHealth`/`PoolHealthKnowledge` 类型与 `poolHealth()`；新增 `components/PoolHealthCard.tsx`（纯展示：总量行 + 知识点行 + 免责声明）；`HomeView` 既有 `Promise.allSettled` 折叠请求，`.home-side` 右列新增 `aria-label="题库体检"` 卡片。零新增 CSS（复用 `.goal-summary/.comparison/.kid/.step-facts/.muted.tiny`）。
- **契约**：`contracts/openapi.yaml` 由 `scripts/generate_openapi.py` 再生成（+39 行，仅新增端点），`check_openapi.py` 通过。

## 实际命令与结果

- `services/api/tests/test_pool_health.py`：**8 passed**（纯函数：空池全零/ seen-unseen 拆分/ 多知识点题只计一次/ 排序与输入顺序无关/ 免责声明在位且无 score 字段；端点：曝光后计数、空科目全零、401、修订新版仍计 1 题）。
- `services/api/tests/test_health_revision.py`：**2 passed**（`/health/live` 缺省 `dev`、显式构建标识透传，ST-017 部署身份核对的基础）。
- `apps/web`：`npm run build` 通过；`npx playwright test` **15 passed / 3 skipped**（新增 `e2e/pool-health.spec.ts` J7/J7b 2/2，chromium）；`npm run test:e2e:ipad` **18 passed**（J7/J7b 在 iPad/WebKit 同绿）。
- J7b 断言零余量知识点显示「暂无未见题余量」且页面不出现非否定语境的「0 分」（缺证据不渲染为 0 分的既有红线在卡片上复证）。

## 限制与未验证（如实）

- 计数为"当前事实快照"：e2e 只断言形状与集合，精确计数由后端单测锁定（J1–J6 会消耗曝光，顺序相关不可断数值）。
- 「题少≠不重要」只是免责口径；不引入知识点 taxonomy、难度或统计推断（YAGNI）。
- 无真实 iPad 设备：UI 断言同样只经 WebKit 仿真通道 + 本机生产栈。
- 远端 CI 未运行（提交推送后由 CI 门禁裁决）。
