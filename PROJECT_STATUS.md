# 书童 Codex 交接时点的真实状态

## 提供的可运行组件

- FastAPI 私有 API（owner Bearer Token）、SQLite 本地开发适配/PostgreSQL 配置、Alembic 基础迁移。
- 来源台账、私有 PDF/图片原件与哈希、本地 PDF 文本/图片 OCR 草稿、人工确认、草稿/审核/发布选择题与修订新版本、曝光记录、自动判分、简单幂等答题、总分学校卷记录、Goal 版本、启发式画像和训练计划。
- React Web/PWA 交互骨架；PWA **只缓存静态壳，不离线缓存学生数据/API**。
- OpenAPI 快照、JSON Schema 验证及反例、Markdown 图片/链接校验、测试、已验证的 GitHub CI、备份模板。

## 尚未实现且不得宣称完成

复杂试卷/公式/图表自动解析、真实资料来源法务评审、并发曝光原子性、正式题池轮换、扫描 PDF 自动 OCR、学校试卷逐题核对、四科完整渲染/评分、正式目标蓝图、可比独立验证与成绩效果评价、访问身份管理、外部部署、自动告警、异地完整恢复。

## 当前环境验证记录（2026-10-18）

ST-001 已完成本地基线与远端 CI 验证，AC-DOC-01/02/03 均通过。完整命令、初始失败及修复证据见 [ST-001 验证记录](docs/quality/st-001-baseline.md)。此结论仅覆盖 ST-001，完整 MVP 与运行灾备仍未完成。

- Python API/业务测试：8 passed；文档检查器测试：2 passed。
- Schema 正反例、22 篇 Markdown 链接/图片、API/OpenAPI 快照一致性：通过。
- 隔离临时 SQLite 数据库 Alembic 初始迁移：通过，`0001 (head)`。
- Web：初始构建因缺少 Vite 类型声明失败；修复后 `npm ci` 与 `npm run build` 通过。
- Zensical：初始严格构建因站点外 Markdown 链接失败；修复后严格构建通过。
- GitHub Actions：仅修改 `AGENTS.md` 的 `4a5dd6f` 触发 push CI，两个作业全部通过；[实际运行](https://github.com/xman900719/pageboy/actions/runs/39117777469)。基线提交和后续文档提交的 CI 也通过。
- PostgreSQL 16.15：ST-002 修订接口的隔离真实并发验证通过（6 轮、每轮 8 请求/8 连接）；完整应用容器联调、VPS/Tailscale 部署、备份还原仍未验证。
- 本地 Python 为 3.14.4，远端 Python 3.12.15 已验证。测试有一条 Starlette/httpx 弃用警告；Actions 有 Node 20 运行时弃用提示，均未导致失败。

## 优先风险

1. 当前曝光是否未见仍有并发争用，应按 ST-004 修复并增加并发测试。
2. 私人身份验证是单用户 token 方案，只适合隔离私网环境，不能公网裸奔。
3. 备份脚本只处理 DB，不覆盖已实现的私有原件；真实数据落库前必须完成联合备份和隔离恢复。
4. `personal_use_reviewed` 仅表示手动标注，不是实际版权法律结论。
5. ST-002 已实现追加修订、重新审核及旧版历史保留；曝光选择仍需 ST-004 原子化与并发验证。


## ST-002 本地验证（2026-10-18）

已实现已发布题的修订草稿接口，新练习使用最新已发布版；旧版、曝光、作答和评分保持不变，同一题换版不恢复未见资格。本地新增 12 项正反例测试通过；另有 6 轮隔离 PostgreSQL 真实并发测试通过，旧历史保持不变。普通门禁为 API/业务 20 passed、6 项 PostgreSQL 集成测试明确 skipped；文档检查器 2 passed，Schema、23 篇 Markdown、OpenAPI、Zensical 严格构建均通过。本轮仅本地提交，ST-002 远端 CI 未运行。验收及兼容/回滚边界见 [ST-002 验证记录](docs/quality/st-002-question-revisions.md)。


## ST-003 本地验证（2026-10-18）

来源台账、原件私有存储、哈希校验、本地 PDF 文本/PNG/JPEG OCR 草稿、人工确认与发布门禁已实现。测试只使用运行时生成的虚构测试数据。SQLite 升降级/再升级及 PostgreSQL 16.15 升级均保留原来源；不代表恢复演练。完整测试与限制见 [ST-003 验证记录](docs/quality/st-003-private-ingestion.md)。本轮仅本地提交，远端 CI、生产部署与联合备份未验证。下一项 ST-004。
