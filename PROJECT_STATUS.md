# 书童 Codex 交接时点的真实状态

## 提供的可运行组件

- FastAPI 私有 API（owner Bearer Token）、SQLite 本地开发适配/PostgreSQL 配置、Alembic 基础迁移。
- 来源记录、草稿/审核/发布选择题、曝光记录、自动判分、简单幂等答题、总分学校卷记录、Goal 版本、启发式画像和训练计划。
- React Web/PWA 交互骨架；PWA **只缓存静态壳，不离线缓存学生数据/API**。
- OpenAPI 快照、JSON Schema 验证及反例、Markdown 图片/链接校验、测试、GitHub CI 草案、备份模板。

## 尚未实现且不得宣称完成

完整内容解析、已发布题更正新版本、资料来源法务评审、安全附件上传与文件哈希、并发曝光原子性、正式题池轮换、OCR、学校试卷逐题核对、四科完整渲染/评分、正式目标蓝图、可比独立验证与成绩效果评价、访问身份管理、外部部署、自动告警、异地完整恢复。

## 当前环境验证记录（2026-10-18）

ST-001 本地基线已验证；用户确认暂保留远端 CI 未验证。完整命令、初始失败及修复证据见 [ST-001 验证记录](docs/quality/st-001-baseline.md)。整体任务不标记全部完成。

- Python API/业务测试：8 passed；文档检查器测试：2 passed。
- Schema 正反例、22 篇 Markdown 链接/图片、API/OpenAPI 快照一致性：通过。
- 隔离临时 SQLite 数据库 Alembic 初始迁移：通过，`0001 (head)`。
- Web：初始构建因缺少 Vite 类型声明失败；修复后 `npm ci` 与 `npm run build` 通过。
- Zensical：初始严格构建因站点外 Markdown 链接失败；修复后严格构建通过。
- GitHub Actions：触发配置静态检查通过；远端运行及仅修改 `AGENTS.md` 的触发实验未验证。
- PostgreSQL 容器联调、VPS/Tailscale 部署、备份还原：均未验证。
- 本地 Python 为 3.14.4，CI 配置为 3.12；CI 环境执行未验证。测试有一条 Starlette/httpx 弃用警告。

## 优先风险

1. 当前曝光是否未见仍有并发争用，应按 ST-004 修复并增加并发测试。
2. 私人身份验证是单用户 token 方案，只适合隔离私网环境，不能公网裸奔。
3. 备份脚本只处理 DB，不覆盖未来图片/附件；真实数据落库前必须完成联合备份和隔离恢复。
4. `personal_use_reviewed` 仅表示手动标注，不是实际版权法律结论。
5. 模型中的试题版本内容只有单向状态流；已发布新版本修订要在 ST-002 实现。
