# 开发环境测试数据与档案政策

> 生效日期：2026-11-15。适用于 `$PAGEBOY_HOME/development` 与所有开发/人工测试入口。

## 1. 默认状态

开发环境**默认空库、空档案**。禁止自动灌入：

- 虚构测试题目、演示题源；
- 虚构校考试卷、答题卡、附件；
- 人工测试临时数据库、种子数据、截图/日志中的虚构档案。

自动化 `pytest` / Playwright 使用临时数据库与 `/tmp` 目录，不属于持久开发环境；其数据仍必须明确标记为虚构，且禁止进入生产。

## 2. Owner 批准门禁

确需在开发环境使用虚构测试数据/档案时，Owner 必须明确批准，并显式提供审批引用：

```bash
PAGEBOY_OWNER_TEST_DATA_APPROVED=1 \
PAGEBOY_OWNER_APPROVAL_REF="<owner-provided-reference>" \
python scripts/seed_demo.py  # 仅限 Owner 批准的虚构演示题；不得用于真实数据
```

- `scripts/seed_demo.py`：未批准时 fail-closed，不写入虚构演示题。
- 旧人工测试脚本 `scripts/run_manual_test_env.py` 已删除；`scripts/run_dev_env.py` 只启动开发库（空库或既有真实库），不自动灌入虚构数据。
- 任何手工向开发库/私有目录注入虚构校考试卷、附件或种子的操作，同样必须先获 Owner 批准并提供审批引用。
- 审批引用只用于本次运行审计，不写入业务数据库；不得把批准变量固化进脚本、`.env` 或 CI。
- Agent 不得自行设置批准变量；必须由 Owner 明确给出批准与引用。

## 3. 2026-11-15 清理审计

已删除：

- 开发私有收件箱中的 5 份 `R2虚构_九年级道德与法治统一练习.docx`；
- `$PAGEBOY_HOME/development/run/manual_test/`（虚构测试库、附件、日志）；
- `/tmp/opencode` E2E 临时库/附件/合成课标标记；
- `apps/web/test-results`、`apps/web/playwright-report` 测试产物；
- 已停止 5173/8000/18765/4173 开发/测试服务，4173 不再使用。
- 已删除 `scripts/run_manual_test_env.py`；开发入口统一为 `scripts/run_dev_env.py`。

明确保留（非虚构）：

- `$PAGEBOY_HOME/development/data/shutong-dev.sqlite3` 中的 2018–2025 北京中考真题来源/题目；
- `data/attachments` 中与这些真实来源关联的附件；
- `data/curriculum_standards` 中的正式课程标准 PDF；
- `data/school-exams/inbox/十月`、`期中` 下的真实学校试卷；
- 生产环境、生产数据与生产服务未触碰。

## 4. 复核

```bash
# 无虚构标记文件
find "$PAGEBOY_HOME/development" -name '*R2虚构*' -o -name '*虚构*'

# 未批准时必须拒绝写入虚构演示题
env -u PAGEBOY_OWNER_TEST_DATA_APPROVED -u PAGEBOY_OWNER_APPROVAL_REF \
  python scripts/seed_demo.py
```

预期：第一条无输出；第二条返回非零并显示“拒绝写入开发环境虚构测试数据”。
