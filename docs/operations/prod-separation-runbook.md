# 开发/生产分离切换手册（同一宿主机）

> 目标：开发（用户 `xc`、仓库目录）与生产（用户 `shutong-prod`、`/media/xc/backup_ext4/pageboy-home/production`）在同一宿主机完全分离；真实 iPad 只访问生产（Cloudflare 隧道入口）。项目暂不对外发布，沿用既有密钥。
> 现状与边界见 [deployment.md](deployment.md)；备份恢复策略只在 [backup-policy.md](backup-policy.md)，操作见 [recovery-runbook.md](recovery-runbook.md)。

## 目标布局

| 项 | 开发 | 生产 |
|---|---|---|
| OS 用户 | `xc` | `shutong-prod`（无口令，仅 `sudo -iu` 进入） |
| 代码 | 开发仓库 | `/media/xc/backup_ext4/pageboy-home/production/repo`（从 `/media/xc/backup_ext4/pageboy-home/production/release.git` 检出） |
| 机密 | 无 | `/media/xc/backup_ext4/pageboy-home/production/env/prod.env`（0600） |
| 附件 | 测试用临时目录 | `/media/xc/backup_ext4/pageboy-home/production/data/attachments` |
| Docker | 开发用户 rootless Docker | 系统 Docker，`shutong-prod` 在 `docker` 组 |
| Compose 项目 | 隔离测试库（临时） | `shutong-prod`（数据卷仍为 `infra_pgdata`） |
| Web 产物 | 开发树 `apps/web/dist`（不影响线上） | `/media/xc/backup_ext4/pageboy-home/production/repo/apps/web/dist` |
| 发布方式 | `git push /media/xc/backup_ext4/pageboy-home/production/release.git HEAD:refs/heads/release` | `git pull` 后 `infra/deploy.sh --web` |

> [!WARNING]
> 在完成第 5 步之前，**不要在开发树里再运行 `infra/deploy.sh`**：`compose.yaml` 已把项目名固定为 `shutong-prod`，会在旧栈旁再起一套。

## 步骤（`[你]` 表示需要你在终端执行）

### 1. 备份并确认可恢复 `[你]`
```bash
cd /media/xc/backup_ext4/code/pageboy/infra
bash backup.sh && echo BACKUP_OK
```
应输出 `BACKUP_OK`。再按 [recovery-runbook.md](recovery-runbook.md) 做一次隔离恢复校验。**未通过不要继续。**

### 2. 排查重复的隧道连接器 `[你]`
宿主机 `cloudflared.service` 当前处于 `activating`（反复启动失败），而 compose 里还有一个 `cloudflared` 容器：
```bash
systemctl status cloudflared --no-pager | head -15
journalctl -u cloudflared -n 30 --no-pager
```
若它属于其他项目的隧道，保持不动。若是书童旧遗留，切换后再停用：`sudo systemctl disable --now cloudflared`。

### 3. 创建生产用户与目录 `[你]`
```bash
cd /media/xc/backup_ext4/code/pageboy
sudo bash infra/provision-prod.sh
```
脚本幂等，不停旧栈、不删除任何文件。完成后**重新登录一次**（或 `newgrp shutong-deploy`），让发布组权限生效。

### 4. 推送代码并在生产检出 `[你]`
先在开发仓库提交本次改动（提交前按 AGENTS.md 完成前端人工测试确认），然后：
```bash
cd /media/xc/backup_ext4/code/pageboy
git push /media/xc/backup_ext4/pageboy-home/production/release.git HEAD:refs/heads/release

sudo -iu shutong-prod bash -c '
  git clone -b release /media/xc/backup_ext4/pageboy-home/production/release.git /media/xc/backup_ext4/pageboy-home/production/repo &&
  cd /media/xc/backup_ext4/pageboy-home/production/repo/infra &&
  ln -s /media/xc/backup_ext4/pageboy-home/production/env/prod.env .env &&
  mkdir -p .local && ln -s /media/xc/backup_ext4/pageboy-home/production/bin/caddy .local/caddy && ln -s /media/xc/backup_ext4/pageboy-home/production/bin/restic .local/restic &&
  cd .. && python3 -m venv .venv && .venv/bin/pip install -q -e services/api
'
# 沿用上一个已部署标签，保证回滚可用
sudo install -o shutong-prod -g shutong-prod -m 644 infra/.local/deployed-tag /media/xc/backup_ext4/pageboy-home/production/repo/infra/.local/deployed-tag
sudo install -o shutong-prod -g shutong-prod -m 644 infra/.local/previous-tag /media/xc/backup_ext4/pageboy-home/production/repo/infra/.local/previous-tag
```
`.venv` 仅用于让备份清单记录正确的迁移版本。

### 5. 切换（会有数分钟停机） `[你]`
```bash
# 5.1 停旧栈（保留数据卷；不加 -v）与旧 caddy
cd /media/xc/backup_ext4/code/pageboy/infra
docker compose -p infra --env-file .env -f compose.yaml -f compose.local.yaml down
kill "$(cat .local/caddy.pid)"

# 5.2 停服后最终同步附件（生产副本，不使用 --delete）
sudo rsync -a --chown=shutong-prod:shutong-prod private-data/attachments/ /media/xc/backup_ext4/pageboy-home/production/data/attachments/

# 5.3 在生产检出里起数据库、部署 API 与 Web、起隧道
sudo -iu shutong-prod bash -c '
  cd /media/xc/backup_ext4/pageboy-home/production/repo/infra &&
  C="docker compose --env-file .env -f compose.yaml -f compose.local.yaml" &&
  $C up -d db && ./deploy.sh --web && $C up -d cloudflared
'

# 5.4 启动生产 Caddy
sudo systemctl enable --now shutong-caddy
```
`deploy.sh` 会执行迁移与冒烟（live/ready/subjects/web，并校验 `env=prod`）。失败时按 [deployment.md](deployment.md) 的回滚方法；旧数据卷 `infra_pgdata` 从未被删除。

### 6. 迁移定时任务 `[你]`
```bash
# 从 xc 的 crontab 去掉书童的两条（其他项目的任务保留）
crontab -l | grep -v 'pageboy/infra' | crontab -
# 生产用户接管备份与隧道自愈
sudo -u shutong-prod crontab - <<'EOF'
0 */4 * * * cd /media/xc/backup_ext4/pageboy-home/production/repo/infra && PATH=/media/xc/backup_ext4/pageboy-home/production/bin:/usr/local/bin:/usr/bin:/bin bash backup.sh >> /media/xc/backup_ext4/pageboy-home/production/logs/backup.log 2>&1
*/10 * * * * /media/xc/backup_ext4/pageboy-home/production/repo/infra/tunnel-watchdog.sh
EOF
sudo -u shutong-prod crontab -l
```

### 7. 验证 `[你]`
```bash
curl -fsS http://127.0.0.1:18000/health/live    # 应含 "env":"prod" 与新 app_revision
curl -fsS http://127.0.0.1:8180/health/live
sudo -u shutong-prod bash -c 'cd /media/xc/backup_ext4/pageboy-home/production/repo/infra && bash backup.sh && echo BACKUP_OK'
```
iPad 端：经公网域名登录、做题、提交，数据应与切换前一致。

### 8. 开发侧改用 rootless Docker，并移出 docker 组 `[你]`
先把开发测试要用的镜像从系统 Docker 导出（宿主机访问镜像仓库代理曾故障，先导出可避免重新拉取）：
```bash
docker save postgres:16 postgres:16-alpine 2>/dev/null | gzip > /tmp/dev-images.tar.gz   # 缺少的镜像会被忽略
sudo apt install -y uidmap dbus-user-session
dockerd-rootless-setuptool.sh install
sudo loginctl enable-linger "$USER"
echo 'export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock' >> ~/.bashrc
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock
gunzip -c /tmp/dev-images.tar.gz | docker load && rm /tmp/dev-images.tar.gz
docker info | grep -i rootless          # 应出现 rootless
sudo gpasswd -d "$USER" docker          # 重新登录后生效
```

### 9. 清理开发树里的生产机密与真实附件 `[你]`
**确认生产稳定运行至少一个备份周期、且 `/media/xc/backup_ext4/pageboy-home/production/data/attachments` 文件数与旧目录一致后**再执行；这里用移动到离线备份位置而不是直接删除：
```bash
cd /media/xc/backup_ext4/code/pageboy/infra
diff <(find private-data/attachments -type f | wc -l) <(sudo find /media/xc/backup_ext4/pageboy-home/production/data/attachments -type f | wc -l) && echo COUNT_MATCH
install -d -m 700 ~/shutong-old-prod-archive
mv .env .local/restic-password private-data ~/shutong-old-prod-archive/
```
归档确认无用后由你自行删除（涉及生产备份密钥，我不会替你删除）。

### 10. 隔离自检 `[你]`
```bash
bash scripts/check_env_isolation.sh
```
全部 `PASS` 才算完成分离。

## 日常发布（分离后）
```bash
# 开发用户：仅在工作区干净、已提交后
git push /media/xc/backup_ext4/pageboy-home/production/release.git HEAD:refs/heads/release
# 生产用户
sudo -iu shutong-prod bash -c 'cd /media/xc/backup_ext4/pageboy-home/production/repo && git pull --ff-only && infra/deploy.sh --web'
```

## 回退（切换失败时）
1. `sudo systemctl disable --now shutong-caddy`
2. 在开发树用旧项目名恢复：`docker compose -p infra --env-file .env -f compose.yaml -f compose.local.yaml up -d`，再 `.local/caddy run --config Caddyfile.local --pidfile .local/caddy.pid &`（工作目录 `infra/`）。
3. 附件以旧目录为准；若切换后产生新附件，先从 `/media/xc/backup_ext4/pageboy-home/production/data/attachments` 同步回来。
