# 贡献约定

个人开发环境可直接使用 feature 分支。提交前运行 README 所列检查；PR 摘要包含修改理由、相关验收 ID、迁移与回滚说明。不要上传私有试卷或学生数据。产品事实只维护于 `docs/` 和 `contracts/`，历史 `reference/legacy/` 不作为当前实现要求。AI 代理还必须遵守 `AGENTS.md`。

## 文档与图表维护

项目采用 Docs-as-Code 静态矢量图预编译方案。**后续新增或修改 Mermaid 图表时，仅需在 `docs/assets/diagrams/*.mmd` 中调整源文件，执行 `make docs` 即可全自动同步重绘 SVG**。文档中统一采用 `![图表说明](../assets/diagrams/*.svg)` 直接引用生成的静态矢量图，并在可折叠块（`<details>`）中保留原始 Mermaid 源码。
