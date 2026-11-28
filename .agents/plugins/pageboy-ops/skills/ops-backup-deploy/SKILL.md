---
name: ops-backup-deploy
description: >-
  Use this skill ONLY when the Owner explicitly authorizes production stack health checks,
  tagged deployment or rollback (ST-017), Cloudflare R2 offsite encrypted backup/restore
  drills (ST-OPS-01), or Cloudflare Tunnel watchdog diagnostics (ST-016).
---

# 生产运维、标签化部署回滚与 R2 异地灾备演练 SOP

> **R3 / R4 风险边界**：本技能涉及的所有写操作或生产变更命令，必须先获得 Owner 显式人工授权与独立备份确认；日常开发期间保持 `pageboy-ops` 插件处于 `disabled` 状态。

## 1. 本机生产栈与隧道只读探针（R0 只读）

在不读取生产机密文件（`/media/xc/backup_ext4/pageboy-home/production` 对开发用户 `xc` 不可读）的前提下，可通过本机环回入口与公网门禁检查运行态：
```bash
# 1. 本机 Caddy 生产反代健康与构建版本身份
curl -fsS http://127.0.0.1:8180/health/live
curl -fsS http://127.0.0.1:8180/health/ready

# 2. 验证外网隧道对管理端路由的 403 CF-Ray 物理阻断（模拟外网头）
curl -s -o /dev/null -w "%{http_code}\n" -H "CF-Ray: simulated-edge" http://127.0.0.1:8180/admin.html
```

## 2. 标签化部署与回滚演练（ST-017 / `infra/deploy.sh` & `infra/rollback.sh`）

- 权威手册：[docs/operations/deployment.md](../../../../docs/operations/deployment.md) 与 [docs/operations/production-environment.md](../../../../docs/operations/production-environment.md)。
- 生产环境部署必须使用带注释的 Git 标签或明确 commit SHA 构建镜像（`shutong-api:api-<rev>`），并在切换前执行完整备份。
- **回滚边界**：`infra/rollback.sh` 仅回滚应用容器镜像并执行 `/health/live` 与业务冒烟校验；**设计上不支持破坏性 Schema 降级回滚**。

## 3. R2 异地联合备份与独立隔离恢复演练（ST-OPS-01 / AC-OPS-01~02）

- 权威策略：修改备份策略只改 [docs/operations/backup-policy.md](../../../../docs/operations/backup-policy.md)，其余手册引用它。
- ST-024-C1/C2 仅允许普通开发用户执行 `.venv/bin/python scripts/smoke_joint_restore.py`（已有原生 PG16；私有 Unix Socket；全合成数据）。禁止运行旧版 Compose 演练、任意 DB URL 恢复、生产 Docker 或旧 R2 恢复脚本；R2 真实快照恢复待 C3 独立授权与门禁。详见 [隔离恢复手册](../../../../docs/operations/recovery-runbook.md)。
- **严禁未授权执行**：`restic forget`、`restic prune`、生产库 `pg_restore` 覆盖或删除生产备份仓库。
