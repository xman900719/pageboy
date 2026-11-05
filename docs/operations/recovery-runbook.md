# 隔离恢复操作手册

请先阅读 [备份策略](backup-policy.md)。**绝不直接覆盖生产数据库**。

## 灾难处理

1. 隔离故障节点、停止写入并记录故障发生/最后成功快照时间。
2. 在另一环境创建独立 PostgreSQL、临时附件目录与最小权限凭据。
3. 通过异地 restic 仓库查快照、恢复到临时目录。先进行 `restic check`，再比对 dump 与附件 SHA-256；备份密钥不得写入 Git。
4. 在隔离数据库使用对应 Postgres 版本执行 `pg_restore`，不要连生产。
5. 恢复对应版本的应用代码/迁移，核对试题版本、答题记录、学校分数、目标版本与附件文件路径。
6. 在隔离环境运行私有 API 冒烟检查和“从答题证据重建画像”测试。
7. 记录实际 RPO、RTO 和恢复材料，人工确认后才可能切换生产访问。

## 推荐方式：一键自动化隔离恢复演练

项目中已将拉取异地快照、启动隔离 PostgreSQL 容器、校验 SHA-256、执行 `restore.sh` 及运行 `smoke_restore_verify.py` 冒烟封装为一键脚本：

```bash
# 默认拉取 latest 快照并在独立临时容器验证，完成后自动清理：
bash scripts/restore_drill.sh

# 亦可指定特定快照 ID：
SNAPSHOT_ID=7f387bab bash scripts/restore_drill.sh
```

## 手工逐步执行流程（隔离环境）

若因特定排错需要分步手工执行，请使用以下真实流程（切勿直接运行未填入实际参数的占位符）：

```bash
cd /media/xc/backup_ext4/code/pageboy/infra

# 1. 在当前子 shell 加载连接凭据（避免泄露在终端历史或环境）
(
  set -euo pipefail
  set -a; source .env; set +a

  # 2. 查询快照列表
  restic snapshots --compact

  # 3. 恢复最新快照至隔离临时目录
  DRILL_DIR=$(mktemp -d /tmp/shutong-drill.XXXXXX); chmod 700 "$DRILL_DIR"
  restic restore latest --tag shutong-foundation --target "$DRILL_DIR/restic"

  # 4. 定位备份解压路径并核验 SHA256SUMS
  BACKUP_DIR=$(dirname "$(find "$DRILL_DIR/restic" -name SHA256SUMS | head -1)")
  ( cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS )

  # 5. 启动临时隔离 PostgreSQL（端口 55432，库名必须以 pageboy 开头以通过安全护栏）
  docker run -d --name pageboy-drill-manual \
    -e POSTGRES_USER=drill -e POSTGRES_PASSWORD=drill_secret_123 \
    -e POSTGRES_DB=pageboy_drill -p 127.0.0.1:55432:5432 \
    postgres:16

  # 等待容器就绪后执行恢复
  sleep 5
  PG_RESTORE_IMAGE=postgres:16 bash restore.sh \
    --backup-dir "$BACKUP_DIR" \
    --database-url postgresql://drill:drill_secret_123@127.0.0.1:55432/pageboy_drill \
    --attachments-dir "$DRILL_DIR/attachments"

  # 6. 运行冒烟测试核验数据与附件
  cd ..
  .venv/bin/python scripts/smoke_restore_verify.py \
    --database-url postgresql+psycopg://drill:drill_secret_123@127.0.0.1:55432/pageboy_drill \
    --attachments-dir "$DRILL_DIR/attachments"

  # 7. 清理临时演练环境
  docker rm -f pageboy-drill-manual
  rm -rf "$DRILL_DIR"
)
```

> [!WARNING]
> `smoke_restore_verify.py` 取题会在演练库内记录一次曝光（业务语义）。该操作仅在隔离库执行，不触碰生产。
