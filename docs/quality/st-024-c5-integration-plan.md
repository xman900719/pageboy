# ST-024-C5 工程集成（候选，非生产放行）

基线 `8e0db96cb58b66af2c7e4d71ed5ad213b6762358`；Issue #33。仅集成运维脚本、测试与文档，不修改 API 业务、数据库迁移或 Web 源码。

- 保留 C1/C2 已通过宿主机演练的 13 文件候选，逐字节核对 v3 实施来源，禁止恢复任意 DB URL、旧 Compose 固定卷演练和旧 R2 入口。
- 真实 API provenance：从已提交的 Git 源码导出构建；OCI revision 与 tag、实际运行镜像 ID、部署状态及本地 Git commit 交叉核对。历史无来源标签为 UNVERIFIED。
- Web provenance：隔离构建绑定完整 Git SHA；无任意 dist + SHA 的记账命令。归档实际 Web 字节并记录 tree SHA 与数量；旧 dist 无记录时来源为 UNVERIFIED。
- v2 备份清单校验四个内容文件，独立 Web 恢复校验路径和树摘要，保留原生 PG16 私有 Unix socket 的合成联合恢复。旧真实快照通用 DB 恢复工具仍未放行。
- CI 保持五个既有作业名，新增 C1/C2 与 C5 单测，B 回归继续验证 snapshot/heartbeat 门禁。执行并检查真实宿主机演练、完整 PR CI 后才能合并；main CI 全绿后才能考虑关闭 Issue #33。生产发布 ST-024-D 单独授权。

取舍：不自动执行生产 API/Web 原子回滚，不归档 API 镜像本体，不回填历史来源；禁用 dirty build 和不匹配 HEAD 的 no-build。生产部署/备份路径及实际网络 npm 构建尚未在本候选中执行。
