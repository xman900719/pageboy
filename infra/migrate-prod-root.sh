#!/usr/bin/env bash
# 书童生产环境根目录迁移脚本（需 root 执行）
# 将生产环境从 /srv/shutong 平滑迁移到 /media/xc/backup_ext4/prod-env/pageboy
# 用法：sudo bash infra/migrate-prod-root.sh [/media/xc/backup_ext4/prod-env/pageboy]
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "需要 root 权限，请执行：sudo bash $0" >&2; exit 1; }
DEV_USER="${SUDO_USER:?请经 sudo 由开发用户执行（需要 SUDO_USER 以配置安全目录与推送权限）}"
PROD_USER=shutong-prod
DEPLOY_GROUP=shutong-deploy
OLD_ROOT=/srv/shutong
NEW_ROOT="${1:-/media/xc/backup_ext4/prod-env/pageboy}"

echo "=========================================================="
echo "书童生产环境迁移向导"
echo "源生产目录: $OLD_ROOT"
echo "目标新目录: $NEW_ROOT"
echo "生产用户:   $PROD_USER"
echo "发布属组:   $DEPLOY_GROUP"
echo "开发用户:   $DEV_USER"
echo "=========================================================="

# 0. 前置检查
[[ -d "$OLD_ROOT" ]] || { echo "错误：旧生产根目录 $OLD_ROOT 不存在！" >&2; exit 1; }
id "$PROD_USER" >/dev/null 2>&1 || { echo "错误：生产用户 $PROD_USER 不存在！" >&2; exit 1; }

# 1. 穿透权限准备：打通 /media/xc 的穿透权限
if [[ "$NEW_ROOT" == /media/xc/* ]]; then
  echo "==> 为 $PROD_USER 配置 /media/xc 穿透权限 (setfacl)..."
  setfacl -m "u:$PROD_USER:--x" /media/xc
  getfacl /media/xc 2>/dev/null | grep -q "user:$PROD_USER:--x" && echo "ACL 配置成功。"
fi

# 2. 停服前基准联合备份
echo "==> 执行迁移前完整快照备份..."
if [[ -f "$OLD_ROOT/repo/infra/backup.sh" ]]; then
  sudo -u "$PROD_USER" bash -c "cd '$OLD_ROOT/repo/infra' && bash backup.sh && echo PRE_MIGRATION_BACKUP_OK" || {
    echo "警告：旧环境触发备份未成功，请检查是否需要继续。" >&2
  }
fi

# 3. 创建目标根目录并同步现有数据
echo "==> 创建目标目录并同步文件 ($OLD_ROOT -> $NEW_ROOT)..."
install -d -o "$PROD_USER" -g "$DEPLOY_GROUP" -m 710 "$NEW_ROOT"
rsync -aHAX --info=progress2 "$OLD_ROOT/" "$NEW_ROOT/"

# 4. 修复新目录环境变量配置
echo "==> 修正新路径下的环境变量 (prod.env)..."
if [[ -f "$NEW_ROOT/env/prod.env" ]]; then
  sed -i "s|$OLD_ROOT|$NEW_ROOT|g" "$NEW_ROOT/env/prod.env"
  chown "$PROD_USER:$PROD_USER" "$NEW_ROOT/env/prod.env"
  chmod 600 "$NEW_ROOT/env/prod.env"
fi
if [[ -f "$NEW_ROOT/env/restic-password" ]]; then
  chown "$PROD_USER:$PROD_USER" "$NEW_ROOT/env/restic-password"
  chmod 600 "$NEW_ROOT/env/restic-password"
fi

# 5. 修复内部软链接与 Git 配置
echo "==> 修正新生产检出内部软链接与 Git 远端配置..."
sudo -u "$PROD_USER" bash <<EOF
  set -e
  cd '$NEW_ROOT/repo/infra'
  ln -sf '$NEW_ROOT/env/prod.env' .env
  mkdir -p .local
  ln -sf '$NEW_ROOT/bin/caddy' .local/caddy
  ln -sf '$NEW_ROOT/bin/restic' .local/restic
  if [[ -d '$NEW_ROOT/repo/.git' ]]; then
    git -C '$NEW_ROOT/repo' remote set-url origin '$NEW_ROOT/release.git' 2>/dev/null || true
  fi
EOF

# 6. 配置 safe.directory
echo "==> 配置 Git safe.directory..."
(cd / && sudo -u "$DEV_USER" git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$NEW_ROOT/release.git") \
  || (cd / && sudo -u "$DEV_USER" git config --global --add safe.directory "$NEW_ROOT/release.git")
(cd / && sudo -u "$PROD_USER" git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$NEW_ROOT/release.git") \
  || (cd / && sudo -u "$PROD_USER" git config --global --add safe.directory "$NEW_ROOT/release.git")
(cd / && sudo -u "$PROD_USER" git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$NEW_ROOT/repo") \
  || (cd / && sudo -u "$PROD_USER" git config --global --add safe.directory "$NEW_ROOT/repo")

# 7. 停服切换（进入停机窗口）
echo "==> 进入切换窗口：停止旧服务并进行增量附件同步..."
systemctl stop shutong-caddy 2>/dev/null || true
if [[ -f "$OLD_ROOT/repo/infra/compose.yaml" ]]; then
  sudo -u "$PROD_USER" bash <<EOF
    cd '$OLD_ROOT/repo/infra'
    docker compose --env-file .env -f compose.yaml -f compose.local.yaml down 2>/dev/null || true
EOF
fi

# 停服后增量附件同步
if [[ -d "$OLD_ROOT/data/attachments" ]]; then
  echo "==> 停服后最终附件增量同步..."
  rsync -aHAX --delete "$OLD_ROOT/data/attachments/" "$NEW_ROOT/data/attachments/"
fi

# 8. 在新路径启动 Docker 服务栈
echo "==> 在新路径启动生产 Docker 服务栈..."
sudo -u "$PROD_USER" bash <<EOF
  set -e
  cd '$NEW_ROOT/repo/infra'
  docker compose --env-file .env -f compose.yaml -f compose.local.yaml up -d db
  docker compose --env-file .env -f compose.yaml -f compose.local.yaml up -d api cloudflared
EOF

# 9. 更新并启动 Systemd Caddy 服务
echo "==> 更新 /etc/systemd/system/shutong-caddy.service 并启动..."
cat > /etc/systemd/system/shutong-caddy.service <<EOF
[Unit]
Description=书童生产入口 Caddy（静态 Web + API 反代，监听 :8180，由 cloudflared 隧道接入）
Documentation=file://$NEW_ROOT/repo/docs/operations/prod-separation-runbook.md
After=network-online.target docker.service
Wants=network-online.target

[Service]
User=$PROD_USER
Group=$PROD_USER
WorkingDirectory=$NEW_ROOT/repo/infra
ExecStart=$NEW_ROOT/bin/caddy run --config Caddyfile.local
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable shutong-caddy
systemctl restart shutong-caddy

# 10. 更新生产用户的定时任务（crontab）
echo "==> 更新 $PROD_USER 的 crontab 定时备份与看门狗任务..."
sudo -u "$PROD_USER" crontab - <<EOF
0 */4 * * * cd $NEW_ROOT/repo/infra && PATH=$NEW_ROOT/bin:/usr/local/bin:/usr/bin:/bin bash backup.sh >> $NEW_ROOT/logs/backup.log 2>&1
*/10 * * * * $NEW_ROOT/repo/infra/tunnel-watchdog.sh
EOF

# 11. 冒烟健康检查
echo "==> 正在等待服务就绪并执行健康探针检查..."
ready=0
for i in {1..30}; do
  if curl -fsS http://127.0.0.1:18000/health/ready >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" -eq 1 ]]; then
  echo "✅ 容器 API 就绪探针通过 (18000)"
  curl -fsS http://127.0.0.1:18000/health/live
  echo ""
else
  echo "❌ 容器 API 探针超时" >&2
fi

if curl -fsS http://127.0.0.1:8180/health/live >/dev/null 2>&1; then
  echo "✅ 宿主 Caddy 反代健康探针通过 (8180)"
  curl -fsS http://127.0.0.1:8180/health/live
  echo ""
else
  echo "❌ 宿主 Caddy 反代探针未通过" >&2
fi

echo "=========================================================="
echo "🎉 生产环境迁移完成！"
echo "新生产根目录: $NEW_ROOT"
echo "注意：原旧生产目录 $OLD_ROOT 依然完整保留作为安全备份，"
echo "在新栈稳定运行至少一个定时备份周期（如半天至一天）前请勿手动删除。"
echo "=========================================================="
