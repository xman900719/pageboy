# 云迁移准备（云中立）

> 未选定云厂商。本文只固化“换主机/上云时必须成立的约束与步骤”；**目标云环境尚未演练，不得写成“已达成”**。恢复目标与保留策略只在 [backup-policy.md](backup-policy.md) 定义。

## 现状对迁移友好的部分
- 配置全部来自环境变量（`infra/.env.example`、`prod.env`），代码中无主机名/云厂商 SDK。
- API 镜像按 git 短 SHA 打标签，可推送到任意镜像仓库。
- 数据只有两处：PostgreSQL（卷 `infra_pgdata`）与私有附件目录（`SHUTONG_ATTACHMENTS_DIR`）。`backup.sh` 将两者联合备份到 S3 兼容仓库（restic），`restore.sh` 可在任何主机恢复。
- 入口为“反代 + 静态 Web”单入口（`Caddyfile` 容器版、`compose.web.yaml`），隧道（cloudflared）是可选项。

## 迁移到云主机的最小步骤
1. 在目标主机按 [prod-separation-runbook.md](prod-separation-runbook.md) 的目录布局准备生产用户与生产根目录（默认 `/media/xc/backup_ext4/prod-env/pageboy`）。
2. 复制 `prod.env`（经安全通道，勿入 Git），把 `SHUTONG_ATTACHMENTS_DIR`、`ATTACHMENTS_DIR`、`RESTIC_PASSWORD_FILE` 指向目标主机路径，`CORS_ORIGINS` 改为新域名。
3. 用 `restore.sh` 从 restic 仓库恢复到隔离位置，核对 `manifest.txt` 的迁移版本，再按 [recovery-runbook.md](recovery-runbook.md) 接入。
4. 使用容器版入口：`docker compose --env-file prod.env -f compose.yaml -f compose.web.yaml up -d --build`（需另配 TLS，或继续使用隧道）。
5. 迁移窗口内停写旧站、做最后一次备份并恢复、冒烟（`/health/live` 的 `env` 必须为 `prod`）后再切 DNS/隧道；旧站保留到验证通过。

## 迁移前仍需决定/验证
- 云厂商与形态（VPS+Compose / 托管 PostgreSQL + 对象存储）。
- 公网入口的 TLS 与访问控制（Cloudflare Access 或同级门禁）；禁止直接把演示令牌方案暴露公网。
- 镜像仓库与镜像保留策略。
- 在目标环境做一次完整的恢复与回滚演练并留记录。
