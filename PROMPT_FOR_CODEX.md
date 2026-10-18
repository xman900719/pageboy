# 可直接交给下一位 agent 的执行 prompt

请接手「书童（Pageboy / ShuTong）」V1.6 工程。用户已要求：**后续所有实施任务由接手 agent 完成**；上一位 agent 只完成交接，不再继续功能开发。请实际推进实现和验证，不停留在建议或计划。

工作目录：`/media/xc/backup_ext4/code/pageboy`。先阅读：

1. `AGENTS.md`、`CODEX_START_HERE.md`。
2. [当前工程 handoff](docs/handoff/st-004-and-remaining.md)。
3. `PROJECT_STATUS.md`、`IMPLEMENTATION_PLAN.md`、`docs/quality/acceptance.md`。
4. 当前任务对应的 `docs/design/`、`contracts/` 与现有代码/测试；`.agent/policies/` 若存在则按需加载，不能声称读过不存在的文件。

**从 ST-004 继续。** ST-001 已完成当时的本地与远端 CI；ST-002/003 已本地验收，但尚未推送。当前接手分支为 `codex/st-003-private-ingestion`，功能基点 `7477df7c9240b6b84b7221a11b1ad6148d68e1b0`，包含 `8f45af3`、`7ca9e1b`。本地 `main` 和仅从远端克隆的代码可能缺少后续实现；先确认提交链，保留已有功能和他人修改。若接手目录不包含这些提交，先报告代码缺口，不重写 ST-002/003，也不擅自 push。

按以下步骤执行：

1. 核实工作树/分支，复跑基线并记录真实结果。已知历史普通门禁为 API 56 passed、6 skipped，文档测试 2 passed；skipped 是可选 PostgreSQL 修订并发测试，不能当作本轮已通过。环境变化造成的差异需解释。
2. 聚焦 ST-004：明确最小练习会话与轮换规则，修复原子曝光及并发幂等。先查 `main.py` 的 `next_item`、`submit_attempt`，现有模型/迁移、客户端、单线程与修订回归测试。先写可暴露竞争的反例，再实施；不盲目扩展架构。
3. 依照 handoff 中的 ST-004 验证矩阵，使用隔离 PostgreSQL、真实 HTTP、独立连接与受控竞争窗口验证：评价首曝不重复、跨版本已见不恢复、相同键同载荷只产生一条有效作答、复用键不同载荷被拒绝、同一曝光不同键并发不重复落库。保留旧历史；记录轮数、请求/连接数、状态分布、行数及清理结果。不要用 ST-002 修订并发结果替代 ST-004 证据，不把小规模正确性验证写成吞吐达标。
4. 每项任务单独实施、验收与本地提交。按依赖继续 ST-005 → ST-006 → ST-007 → ST-008；ST-009 随变更持续同步。ST-OPS-01 必须在首次真实长期数据落库前完成实际联合恢复，ST-OPS-02 在相应运行环境就绪后执行。外部环境或授权缺失时清楚记录阻塞，继续不依赖它的已授权本地工作，不能假造完成。
5. 严守 DRY、KISS、YAGNI、SOLID、组合复用和 Docs as Code。保持 FastAPI 模块化单体与 `guidance.py` 纯业务计算；禁止覆盖发布版本/历史、用学校总分虚构考点分、将训练已见题认定为独立未见题、用未审核 AI 答案正式判分或预测未经校准的中考分数。
6. API 改动生成并校验 `contracts/openapi.yaml`；结构改动补 Schema/显式迁移/已有库升级测试；代码、测试、契约、必要文档同提交。只使用“虚构测试数据”，不提交私有原件、个人信息、密钥或备份。真实灾备目标以实际演练为证，策略只在 `docs/operations/backup-policy.md` 维护。

常用门禁（从根目录执行，先确认 `.venv` 和系统解析工具可用）：

```bash
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
# 修订并发回归，需要 Docker，使用自动清理的独立临时 PostgreSQL
.venv/bin/python scripts/test_revision_concurrency.py
# 只有 API 变更时生成，然后校验
.venv/bin/python scripts/generate_openapi.py
.venv/bin/python scripts/check_openapi.py
```

不要对未知数据库执行迁移，不自动 push、发布、部署或修改外部系统。本 prompt 不扩大历史推送授权；生产删除/回滚/备份覆盖等必须另获明确授权和独立备份确认。可逆本地实现与必要验证无需反复请求确认。

每项任务完成时，仅按四项汇报：**结果 / 范围 / 验证证据 / 剩余事项**。必须给出实际命令与结果、通过/失败/未验证、迁移回退边界、提交 SHA 和下一任务 ID；未验证不得标记完成。接手多个 agent 时明确文件/任务所有权，不覆盖其他人的编辑，并在切换时更新 handoff。
