# ST-004 验证记录：练习会话、轮换、原子曝光与作答幂等

日期：2026-10-19。分支 `codex/st-003-private-ingestion`（仅本地提交，未推送）。验收 ID：AC-PRC-01、AC-VAL-01。全部测试数据为运行时生成的虚构测试数据；并发测试使用自动创建并清理的独立 PostgreSQL 容器，不触碰任何真实库。

## 实现（最小范围）

- **最小无状态练习会话与确定性轮换**：training 按（该学习者对逻辑题的全版本曝光次数, created_at, id）升序在全部候选中轮换，不再总返回首题；evaluation 仅选曝光次数==0 的逻辑题，无则 404 `NO_ELIGIBLE_QUESTION`；排除未发布题、遵循最新发布版本规则、支持 knowledge_id 过滤，均保持既有语义。
- **曝光原子化**：`exposures` 新增非规范化列 `question_id`（迁移 `0003` 回填），部分唯一索引 `uq_exposure_first_unseen (learner_id, question_id) WHERE is_unseen_at_exposure` 在数据库级保证"每学习者每逻辑题至多一次未见首曝认定"，跨版本、跨 purpose。并发抢曝失败者：evaluation 换下一未见候选（绝不给已见题落 evaluation 曝光），training 重查 seen 后以复练身份重插 `is_unseen_at_exposure=false`。
- **作答幂等约束化**：`answer_attempts` 新增唯一索引 `uq_attempt_exposure (exposure_id)`；`submit_attempt` 改为提交点约束裁决（同键同载荷→`already_recorded` 返回同一持久行；同键异载荷→409 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`；同曝光异键→409 `EXPOSURE_ALREADY_SUBMITTED`；约束外异常→如实抛出），删除旧的"曝光已有作答"前置查询（其竞争交错曾把幂等重试误答 409，见下文 red 证据）。
- **API 签名与响应字段未变**：`contracts/openapi.yaml` 快照一致性校验通过，无需重新生成。

## 实际命令与结果

### Red（实现前反例，2026-10-19）

- `cd services/api && python -m pytest -q` → **1 failed（`test_training_rotates_through_pool`：6 次训练取题只返回同一道排序首题）**, 66 passed。
- `python scripts/test_practice_concurrency.py`（隔离 PostgreSQL 16.15，8 请求/8 独立连接/轮）→ **13 failed / 6 passed**：evaluation/training 首曝竞争 `UniqueViolation: uq_exposure_first_unseen` 未处理→500；同键/同曝光作答竞争→500；一轮 natural 模式中旧 handler 把**同键同载荷幂等重试误答 409 `EXPOSURE_ALREADY_SUBMITTED`**（语义缺陷实锤）。通过项为时序串行化场景与跨版本回归护栏。

### Green（实现后，2026-10-19）

- `PATH="$PWD/.venv/bin:$PATH" make verify` → API **67 passed, 25 skipped**（skipped 为可选 PostgreSQL 并发测试：修订 6 项 + 练习 19 项，由下方脚本在真库执行）；JSON Schema 正反例、25 篇 Markdown 链接/图片、文档检查器 2 passed、`check_openapi` PASS。
- `.venv/bin/zensical build --strict` → 无问题。
- **SQLite 隔离库迁移往返**（`tests/test_practice_migration.py`，随套件通过）：0001→head→`alembic check`→种子数据→downgrade 0002（列/索引删除、5 表行数保留）→head（`question_id` 回填还原、NULL==0、两条唯一约束生效）→`alembic check`。
- `python scripts/test_practice_concurrency.py`（隔离 PostgreSQL 16.15 容器 pageboy-st004-edfe0184e5c5，用后清理）→ **EXIT 0**：
  - 迁移腿：`upgrade head`→`check`→psql 种子→`downgrade 0002`→`upgrade head`→`check`，断言 `exposures.question_id` 回填为预期值、NULL 计数==0，通过（PostgreSQL 侧 alembic 往返与契约一致）。
  - **19/19 并发测试通过（6.07s，每测试 8 请求/8 独立后端连接，零 500）**：
    | 场景 | 轮数×模式 | 结果 |
    |---|---|---|
    | evaluation 首曝竞争（3 题池） | 3×natural + 3×colliding | 每轮恰 3×200（题各不同、unseen=true）+ 5×404；每逻辑题 ≤1 条 unseen |
    | training 首曝竞争（1 题池） | 1×natural + 1×colliding | 8×200、8 条曝光、恰 1 条 `is_unseen_at_exposure=true` |
    | 同键同载荷并发 | 3×natural + 3×colliding | 8×201（1 recorded + 7 already_recorded）、单行、全部响应同一 id 与得分 |
    | 同键异载荷并发 | 1×natural + 1×colliding | 1×201 + 7×409 幂等键冲突、单行 |
    | 同曝光异键并发 | 1×natural + 1×colliding | 1×201 recorded + 7×409 `EXPOSURE_ALREADY_SUBMITTED`、单行、无失败事务残留 |
    | 跨版本已见（发布 v2 后并发 evaluation） | 1×natural | 8×404、无新曝光、v1 曝光/作答不变 |

## 限制与未验证

- 并发验证为小规模正确性证明（8 请求/轮、受控竞争窗、真实 HTTP + 独立连接），**不代表吞吐或生产压测达标**。
- 远端 CI 未运行；前端未改动、未重新构建；ST-008 用户旅程验证未做。
- 遗留库若已存在重复未见认定或同曝光双作答（仅旧并发缺陷可产生），`0003` 索引创建会诚实失败需人工裁决；SQLite 下该失败点非原子（迁移 docstring 已注明）。未在含此类脏数据的库上演练。
- 部分唯一索引依赖 `question_id` 恒被写入（模型列注释已声明）；当前唯一写入者是 `next_item`。

下一项任务：**ST-005**（数学证据—差距—计划—独立复测纵向用例）。
