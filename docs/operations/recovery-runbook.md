# 隔离恢复操作手册（待真实演练）

请先阅读 [备份策略](backup-policy.md) 并确认目标状态为 UNVERIFIED。**绝不直接覆盖生产数据库**。

## 灾难处理

1. 隔离故障节点、停止写入并记录故障发生/最后成功快照时间。
2. 在另一环境创建独立 PostgreSQL、临时附件目录与最小权限凭据。
3. 通过异地 restic 仓库查快照、恢复到临时目录。先进行 `restic check`，再比对 dump 与附件 SHA-256；备份密钥不得写入 Git。
4. 在隔离数据库使用对应 Postgres 版本执行 `pg_restore`，不要连生产。
5. 恢复对应版本的应用代码/迁移，核对试题版本、答题记录、学校分数、目标版本与附件文件路径。
6. 在隔离环境运行私有 API 冒烟检查和“从答题证据重建画像”测试。
7. 记录实际 RPO、RTO 和恢复材料，人工确认后才可能切换生产访问。

## 建议手工命令骨架（替换所有占位符后在隔离环境执行）

```bash
restic snapshots
restic restore <SNAPSHOT_ID> --target /secure/isolated-restore
sha256sum -c /secure/isolated-restore/SHA256SUMS
createdb -h 127.0.0.1 -U recovery_operator shutong_recovery
pg_restore -h 127.0.0.1 -U recovery_operator -d shutong_recovery --no-owner /secure/isolated-restore/postgres.dump
```

上面脚本还需要根据 `restic restore` 的实际目录结构调整路径。未实现文件存储前，附件步骤只能标记 N/A；已包含附件的实际数据绝不能省略联合恢复验证。`ST-OPS-01` 必须产出**真实演练报告**。
