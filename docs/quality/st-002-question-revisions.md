# ST-002 已发布题修订验证记录

日期：2026-10-18。验收：AC-CNT-02、INV-01/02/03/06；仅使用虚构测试数据。本地功能验收及隔离 PostgreSQL 真实并发验证已完成；任务分支尚未推送，远端 CI 未运行。

## 实现范围

- 新增 owner 接口 `POST /api/admin/questions/{version_id}/revisions`，复用完整 `QuestionIn`，以 `QuestionRevisionOut` 返回新草稿的 ID、逻辑题 ID、版本号和状态。
- 修订保留来源、逻辑题和原版，按所有版本的最大编号加一；草稿重新审核发布，不继承原版审批。
- 新练习只选每题最高已发布版本，任意版本曾曝光即视为该逻辑题已见。已有曝光/作答继续绑定旧版，历史评分不重算。
- `contracts/openapi.yaml` 由真实 API 重新生成；无需修改 ORM 或数据库迁移。没有修改纯业务 `guidance.py`。

完整接口语义见 [内容导入与修订](../design/ingestion.md)，不在此复制字段合同。

## 实际测试证据

基线命令：`PATH="$PWD/.venv/bin:$PATH" make verify`。修改前 8 项 API/业务测试、2 项检查器测试、Schema、Markdown 和 OpenAPI 全部通过。

先添加回归测试后执行：

```bash
.venv/bin/python -m pytest services/api/tests/test_question_revisions.py -q
```

初次得到 **9 failed、1 passed**，失败原因是修订路由不存在而返回 404；其中版本不存在反例同样返回 404，单独通过并不能证明功能存在。实现后补齐来源再审核和编号冲突测试，最终 **12 passed**。覆盖：

1. 原版、旧曝光和旧作答的全字段快照不变；新旧作答均指向对应版本。
2. 更改题干、答案、标签和满分后，新版使用新内容判分，旧曝光延迟提交仍按旧答案/满分判分；旧幂等提交重放保持原记录。
3. 新草稿不能直接发布，不继承审核标记或发布时间；来源变为未确认后再次发布被拒绝。
4. 新草稿不替代发布版；版本 3 先发布、版本 2 后发布，练习仍选择版本 3。
5. 基于旧发布版继续创建草稿，编号不重复；同一题换版后不得充当未见题，知识点过滤不得复活旧版。
6. 未认证、版本不存在、未发布版本、更换来源、非法选项/分数、缺必填字段均拒绝且不写入新版本。
7. 模拟读取过期最大版本号，由真实 SQLite 唯一约束触发冲突，接口返回 409 并回滚，已有草稿未覆盖。

生成契约及全门禁命令：

```bash
.venv/bin/python scripts/generate_openapi.py
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
git diff --check
```

结果：API/业务 **20 passed**（包含新增 12 项修订测试），文档检查器 **2 passed**；Schema 正反例、23 篇 Markdown 链接/图片、OpenAPI 快照一致性、Zensical 严格构建及 `git diff --check` 均通过。测试保留一条既有 Starlette/httpx 弃用警告。

## 兼容、迁移与回滚

- 接口为新增；创建题目仍使用原有请求格式。修订请求是完整更正内容，来源必须保持一致。
- 复用既有表、外键和唯一约束，无迁移、无历史数据回写；不删除已发布版本或答题记录。
- 回退代码会移除修订入口并恢复原有选题语义，已有新版本和历史记录保留；若需运行回退，应先在隔离环境核对选题行为。
- 已补齐修订接口的隔离 PostgreSQL 真实 HTTP 并发验证，见下文。覆盖单实例应用、多线程请求与独立数据库连接；不代表多实例部署压测、曝光/作答原子性或轮换验收，后者仍属 ST-004。
- 基线已有 Starlette/httpx 弃用警告，不作为功能失败处理。下一项任务为 ST-003。


## PostgreSQL 真实并发补验（2026-10-18）

实际执行：

```bash
.venv/bin/python scripts/test_revision_concurrency.py
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
git diff --check
```

运行器需要本机 Docker 可用、已安装 API 测试依赖及可获取 `postgres:16`。它创建独立临时容器，数据库目录使用 tmpfs，不挂载宿主数据；仅映射随机回环端口，密码临时生成，不写入仓库。pytest 为每轮创建随机独立 schema，以真实 Uvicorn HTTP 服务接受请求；每个请求使用独立 SQLAlchemy Session。结束后清理 schema、HTTP 服务和本轮容器，不操作已有数据库或服务。

本次镜像：PostgreSQL **16.15**（Debian 16.15-1.pgdg13+2），仓库摘要 `postgres@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6`。使用本地 Python 3.14.4。并发测试中没有模拟 SQL 返回值、IntegrityError 或 HTTP 响应；强制竞争仅在真实 `SELECT max(version)` 完成之后用线程屏障阻挡后续写入。

| 场景 | 轮次 | 并发修订请求 | PostgreSQL 后端连接数 | 201 成功 | 409 冲突 | 冲突重试成功 |
|---|---|---|---|---|---|---|
| 自然竞争 | 1 | 8 | 8 | 3 | 5 | 5 |
| 自然竞争 | 2 | 8 | 8 | 4 | 4 | 4 |
| 自然竞争 | 3 | 8 | 8 | 4 | 4 | 4 |
| 读后同时写入 | 1 | 8 | 8 | 1 | 7 | 7 |
| 读后同时写入 | 2 | 8 | 8 | 1 | 7 | 7 |
| 读后同时写入 | 3 | 8 | 8 | 1 | 7 | 7 |

结果：**6 passed**，48 个并发修订请求与 34 个冲突后重试均符合预期，无 500。每轮只持久化成功请求对应的草稿，无失败残留；重试后版本号恰为 1–9，版本 ID/编号唯一。原版所有字段、逻辑题、曝光和作答快照在并发前后及重试后完全一致。自然竞争的成功数随调度可能变化，不应固定要求每次相同；强制竞争固定断言 1 成功、7 冲突。无需修改业务实现、OpenAPI 或数据库结构。

首次运行有 6 项测试失败：本机环境设置了 SOCKS 代理，HTTPX 在创建本地客户端时因缺少 socksio 失败，尚未调用修订接口。测试客户端改为 `trust_env=False`，避免本地测试流量受环境代理影响，随后上述 6 项全部通过。临时容器两次运行均已清理，容器列表查询未发现本次测试遗留。

未设置专用测试数据库环境时，普通 `make verify` 会明确跳过这 6 项集成测试，不将其记为通过；真实并发证据来自上述隔离运行器。普通门禁结果为 **20 passed、6 skipped**，文档检查器 **2 passed**，契约与文档检查通过。既有 Starlette/httpx 弃用警告保留。
