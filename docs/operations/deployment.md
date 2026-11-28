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

当前 Compose 已将 ST-003 私有原件挂载到 `/var/lib/shutong/attachments` 的 `private_files` 卷，但不包含生产前端反向代理或证书管理；**禁止将它描述为完整生产就绪部署**。上线前仍须验证健康检查、固定镜像版本及配置告警，并通过恢复门禁。

恢复目标与备份保留策略只在 [backup-policy.md](backup-policy.md) 定义；操作命令在 [recovery-runbook.md](recovery-runbook.md)。

## 本机生产栈更新与回滚（ST-017）

本机模式栈（`compose.yaml` + `compose.local.yaml`）的 API 更新/回滚已脚本化，替代手工 `up -d --build`：

```bash
infra/deploy.sh                 # 构建 shutong-api:api-<git短SHA> → 迁移 head → 替换 api → 冒烟
infra/deploy.sh --web           # 同前，并先重建 apps/web/dist（宿主 caddy 伺服该目录）
infra/rollback.sh               # 回滚到上一个已部署标签（infra/.local/previous-tag）
infra/rollback.sh api-1a2b3c4   # 显式回滚到指定本地镜像标签
```

事实与边界（实现时如实记录）：

- 镜像按 git 短 SHA 打标签；`SHUTONG_APP_REVISION` 透传进容器，`/health/live` 因此返回 `app_revision`，"哪个构建在服务"可经应用自身证明，不靠宿主机 `docker inspect`。
- 部署流程：构建 → 同镜像一次性容器 `alembic upgrade head`（幂等，head 已达成时为无操作）→ 仅替换 api 服务（db 卷与附件 bind mount 不触碰）→ 就绪等待 + 冒烟（live/ready/subjects/web 四项）。
- **回滚只切镜像，不降级 schema**：结构回滚属数据决策，须人工判断 + 独立备份确认，流程见 [recovery-runbook.md](recovery-runbook.md)。
- 回滚目标镜像必须仍在本地：`deploy.sh` 不清理旧镜像，但也**没有镜像保留策略**（未演练磁盘压力），使用方不得自行 `docker image prune`。
- `--web` 会执行 `npm ci && npm run build`；未传该标志时 dist 不更新（Web 为静态产物，宿主 caddy 直接伺服 `apps/web/dist`）。
- 演练与实测证据见 [ST-017 记录](../quality/st-017-deploy-rollback-drill.md)。

## 环境隔离（开发 / 测试 / 生产）

- 运行环境由 `SHUTONG_ENV`（`dev`/`test`/`prod`，缺省 `dev`）标识并经 `/health/live` 的 `env` 字段自报；生产 compose 固定为 `prod`，手工测试环境为 `test`。
- `scripts/seed_demo.py` 探测到目标 `env=prod` 即拒绝写入虚构演示数据。
- `infra/deploy.sh` 在工作区有未提交改动时拒绝部署（退出码 3），需显式 `--allow-dirty`；冒烟另校验 `env=prod`。
- 真实 iPad 只访问生产（Cloudflare 隧道入口）；`scripts/run_dev_env.py` 的开发服务仅监听 `127.0.0.1`，由宿主机桌面模拟机访问。
- 沿用现有密钥，暂不轮换；项目暂不对外发布。
- 同机分离的目录/用户/Docker/发布流程与切换命令见 [prod-separation-runbook.md](prod-separation-runbook.md)（**脚本与手册已就绪，切换需 owner 以 sudo 执行，未执行前现网仍是旧布局**）；云迁移准备见 [cloud-migration.md](cloud-migration.md)；自检脚本 `scripts/check_env_isolation.sh`。


## ST-024-B 候选发布门禁（未执行生产发布）

推荐入口 `scripts/release_prod.sh --dry-run`；必须在干净 main 上，实时比对 origin/main，使用已认证的 GitHub CLI（`gh`）核验该 SHA 最新 push workflow 的五个作业。正式发布须另获 Owner 授权并传 `--approve-sha=<完整SHA>`，不允许非 main。生产工作树先校验并快进到指定提交（不启动服务），再用新备份脚本确认异地快照，随后才允许构建/迁移/切换。构建与迁移显式继承同一镜像标签。禁止以本地演练快照替代发布备份；直接调用底层部署/回滚脚本只限授权的独立运维操作，不代表通过一键发布门禁。实际恢复与版本兼容性仍需 ST-024-C，生产发布需 ST-024-D 单独授权。


## ST-024-C5 候选来源证明

`deploy.sh` 的 API 构建从干净 Git 提交导出构建上下文，镜像记录完整 OCI revision；启动后核验运行镜像 ID。`--allow-dirty` 不再允许，`--no-build` 仅接受与当前干净 HEAD 相符的镜像；历史版本另走授权回滚。`--web` 从同一干净提交的独立导出树运行 `npm ci`、`npm run build`，再更新 dist 和本地 `.local/web-provenance.json`；失败不写入虚假的成功记录。构建需要 Python 3.11+（tarfile data filter）、flock、Git、Node/npm、Docker，首次构建使用独立 npm 缓存，网络受限时会失败停止。

旧 Web 没有来源记录时，先备份原始可用产物并标为 UNVERIFIED，不回填。`rollback.sh` 仍为 API-only，C5 不提供生产原子 API/Web 切换或自动 DB 降级；需按恢复手册确认配对与兼容性。Web 目录更新与 API 切换不是跨服务原子事务。正式生产发布另行授权，C5 不执行。
