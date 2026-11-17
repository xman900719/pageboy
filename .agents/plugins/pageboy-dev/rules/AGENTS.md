# Pageboy Dev Plugin Rules

## 1. CodeGraph 符号与调用链优先检索

当仓库根目录存在 `.codegraph/` 索引时，在需要理解模块结构、查找函数定义、追踪跨文件调用链或评估修改影响面时，**优先使用 `codegraph` MCP 工具**（而非盲目执行多次 `grep`/`find`）：
- `codegraph_explore`：一次调用获取相关符号源码及完整调用路径（含动态分发路径）。
- `codegraph_node`：读取单个符号源码与上下游依赖（callers / callees）。
- `codegraph_impact` / `codegraph_affected`：分析修改某个符号的影响范围及对应的受影响测试文件。

## 2. 按需加载领域 Skills 路由

遇到以下领域任务时，主动读取并遵循对应 Skill 的标准作业程序（SOP）：
- **全栈测试、契约、OpenAPI、Docs as Code 与环境隔离验证**：激活 `verify-and-ci`。
- **前端（`apps/web/`）开发、iPadOS 模拟机启动与选项式人工验收门禁**：激活 `frontend-ipad-acceptance`。
- **学校考试五字段同步、`k12100` 隔离采录、多学科报告解析、2022 课标与 135 知识点校验**：激活 `school-exam-and-corpus`。
- **生产部署、回滚、R2 异地备份恢复演练與 Cloudflare 隧道巡检**：需先由 Owner 启用 `pageboy-ops` 插件并激活 `ops-backup-deploy`。
