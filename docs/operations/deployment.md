# 运行环境与部署

## 开发

根目录 README 提供 SQLite 和本地启动步骤。

## 私有云/本地常驻服务器（部署模板，未现场验证）

建议个人私有 Ubuntu LTS 主机或云主机，2 vCPU / 4 GB RAM / 80GB SSD 为**初步估算非实测容量**。Docker Compose 管理 FastAPI + PostgreSQL；前端构建后托管于同主机内网反向代理（部署代理/证书尚需 Codex/运维补充）。只经 Tailscale/VPN 加 HTTPS 访问，别把演示用 token 验证直接发布公网。

```bash
cp infra/.env.example infra/.env
# 必须替换随机强密码与私有令牌，并检查文件权限
chmod 600 infra/.env
cd infra
# 首次必须先初始化数据库，再启动 API
# docker compose --env-file .env -f compose.yaml up -d db
# docker compose --env-file .env -f compose.yaml run --rm api alembic upgrade head
# docker compose --env-file .env -f compose.yaml up -d api
```

当前 Compose 不包含生产前端反向代理、证书管理或完整附件存储挂载；**禁止将它描述为完整生产就绪部署**。增加服务健康检查、镜像版本固定及告警，部署前通过恢复门禁。

恢复目标与备份保留策略只在 [backup-policy.md](backup-policy.md) 定义；操作命令在 [recovery-runbook.md](recovery-runbook.md)。
