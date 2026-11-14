#!/usr/bin/env bash
# 书童 (Pageboy) Home 目录搭建与开发/生产双环境彻底迁移脚本（幂等）
# 目标：
#   - 开发运行时数据与状态全部迁入 /media/xc/backup_ext4/pageboy-home/development (0700 xc:xc)
#   - 生产环境从 /media/xc/backup_ext4/prod-env/pageboy 迁入 /media/xc/backup_ext4/pageboy-home/production (0710 shutong-prod:shutong-deploy)
#   - 源码仓库 /media/xc/backup_ext4/code/pageboy 保持零运行时数据残留
# 用法：
#   bash infra/setup-pageboy-home.sh --dev-only       # 仅搭建并迁移开发环境（无需 sudo）
#   sudo bash infra/setup-pageboy-home.sh --prod-only # 仅迁移生产环境（需要 root）
#   sudo bash infra/setup-pageboy-home.sh             # 完整迁移开发与生产环境
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_ROOT="${PAGEBOY_HOME:-/media/xc/backup_ext4/pageboy-home}"
DEV_HOME="$HOME_ROOT/development"
PROD_HOME="$HOME_ROOT/production"
OLD_PROD_ROOT="${OLD_PROD_ROOT:-/media/xc/backup_ext4/prod-env/pageboy}"
PROD_USER="shutong-prod"
DEPLOY_GROUP="shutong-deploy"

mode="all"
for arg in "$@"; do
  case "$arg" in
    --dev-only) mode="dev" ;;
    --prod-only) mode="prod" ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

setup_dev() {
  local dev_user="${SUDO_USER:-$(id -un)}"
  local dev_group
  dev_group="$(id -gn "$dev_user")"

  echo "=========================================================="
  echo "1. 搭建并迁入开发环境 Home: $DEV_HOME"
  echo "=========================================================="

  install -d -m 755 "$HOME_ROOT"
  install -d -o "$dev_user" -g "$dev_group" -m 700 \
    "$DEV_HOME" "$DEV_HOME/data" "$DEV_HOME/data/attachments" \
    "$DEV_HOME/data/curriculum_standards" "$DEV_HOME/bin" "$DEV_HOME/logs" "$DEV_HOME/run"

  if [[ ! -f "$DEV_HOME/home.json" ]]; then
    cat > "$DEV_HOME/home.json" <<'EOF'
{
  "format_version": 1,
  "workspace_id": "pageboy-development",
  "environment": "development"
}
EOF
    chown "$dev_user:$dev_group" "$DEV_HOME/home.json"
    chmod 600 "$DEV_HOME/home.json"
  fi

  # 1.1 迁移 SQLite 开发库
  if [[ -f "$REPO_ROOT/services/api/shutong-dev.sqlite3" ]]; then
    if [[ ! -f "$DEV_HOME/data/shutong-dev.sqlite3" ]]; then
      mv "$REPO_ROOT/services/api/shutong-dev.sqlite3" "$DEV_HOME/data/shutong-dev.sqlite3"
    else
      mv "$REPO_ROOT/services/api/shutong-dev.sqlite3" "$DEV_HOME/logs/dup-api-shutong-dev.sqlite3.bak"
    fi
  fi
  if [[ -f "$REPO_ROOT/apps/web/shutong-dev.sqlite3" ]]; then
    mv "$REPO_ROOT/apps/web/shutong-dev.sqlite3" "$DEV_HOME/logs/legacy-web-shutong-dev.sqlite3.bak"
  fi

  # 1.2 迁移开发私有附件
  for src_att in "$REPO_ROOT/services/api/private-data/attachments" "$REPO_ROOT/private-data/attachments"; do
    if [[ -d "$src_att" ]]; then
      rsync -a "$src_att/" "$DEV_HOME/data/attachments/"
    fi
  done
  rm -rf "$REPO_ROOT/services/api/private-data" "$REPO_ROOT/private-data/attachments"

  # 1.3 迁移四科官方课标 PDF 原件
  if [[ -d "$REPO_ROOT/private-data/curriculum_standards" ]]; then
    rsync -a "$REPO_ROOT/private-data/curriculum_standards/" "$DEV_HOME/data/curriculum_standards/"
    rm -rf "$REPO_ROOT/private-data"
  elif [[ -d "$REPO_ROOT/private-data" ]]; then
    rm -rf "$REPO_ROOT/private-data"
  fi

  # 1.4 清理开发树下残留 Caddy 进程并迁出 infra/.local
  if [[ -f "$REPO_ROOT/infra/.local/caddy.pid" ]]; then
    local caddy_pid
    caddy_pid="$(cat "$REPO_ROOT/infra/.local/caddy.pid" 2>/dev/null || true)"
    if [[ -n "$caddy_pid" ]] && kill -0 "$caddy_pid" 2>/dev/null; then
      echo "停止开发树残留 Caddy 进程 (PID $caddy_pid)..."
      kill "$caddy_pid" || true
      sleep 1
    fi
  fi
  pkill -u "$dev_user" -f "$REPO_ROOT/infra/.local/caddy" 2>/dev/null || true

  if [[ -d "$REPO_ROOT/infra/.local" ]]; then
    for bin_name in caddy restic; do
      if [[ -f "$REPO_ROOT/infra/.local/$bin_name" ]]; then
        mv -f "$REPO_ROOT/infra/.local/$bin_name" "$DEV_HOME/bin/$bin_name"
        chmod 700 "$DEV_HOME/bin/$bin_name"
      fi
    done
    for log_item in logs pre-clean-backup deployed-tag previous-tag; do
      if [[ -e "$REPO_ROOT/infra/.local/$log_item" ]]; then
        rsync -a "$REPO_ROOT/infra/.local/$log_item" "$DEV_HOME/logs/"
      fi
    done
    rm -rf "$REPO_ROOT/infra/.local"
  fi

  chown -R "$dev_user:$dev_group" "$DEV_HOME"
  chmod 700 "$DEV_HOME" "$DEV_HOME/data" "$DEV_HOME/data/attachments"
  echo "✓ 开发环境已彻底迁入 $DEV_HOME，代码仓库已清理干净。"
}

setup_prod() {
  [[ $EUID -eq 0 ]] || { echo "错误：迁移生产环境需要 root 权限（请使用 sudo bash $0）" >&2; exit 1; }
  local dev_user="${SUDO_USER:?请经 sudo 由开发用户执行（需要 SUDO_USER 以配置发布权限）}"
  id "$PROD_USER" >/dev/null 2>&1 || { echo "错误：生产用户 $PROD_USER 不存在！" >&2; exit 1; }
  [[ -d "$OLD_PROD_ROOT" ]] || { echo "错误：源生产目录 $OLD_PROD_ROOT 不存在！" >&2; exit 1; }

  echo "=========================================================="
  echo "2. 搭建并迁入生产环境 Home: $PROD_HOME"
  echo "=========================================================="

  # 2.1 确保穿透权限与目录结构
  if [[ "$PROD_HOME" == /media/xc/* ]]; then
    setfacl -m "u:$PROD_USER:--x" /media/xc
  fi
  install -d -m 755 "$HOME_ROOT"
  chmod 755 "$HOME_ROOT"

  # 2.2 探测正在运行的旧栈项目名，先清理可能残留的半启动 shutong-prod，再执行迁移前基准联合备份
  local active_proj=""
  active_proj="$(sudo -u "$PROD_USER" docker ps --filter "publish=18000" --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | head -n1 || true)"
  if [[ -n "$active_proj" && "$active_proj" != "shutong-prod" ]]; then
    sudo -u "$PROD_USER" docker rm -f $(sudo -u "$PROD_USER" docker ps -aq --filter "label=com.docker.compose.project=shutong-prod" 2>/dev/null) 2>/dev/null || true
  fi
  if [[ -z "$active_proj" ]]; then
    active_proj="$(sudo -u "$PROD_USER" docker ps --filter "name=postgres" --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | grep -E '^(infra|shutong-prod)$' | head -n1 || true)"
  fi
  if [[ -f "$OLD_PROD_ROOT/repo/infra/backup.sh" && -f "$OLD_PROD_ROOT/env/prod.env" && -n "$active_proj" ]]; then
    echo "执行迁移前生产基准备份 (project=$active_proj)..."
    sudo -u "$PROD_USER" bash -c "
      cd '$OLD_PROD_ROOT/repo/infra'
      PATH='$OLD_PROD_ROOT/bin':\$PATH ENV_FILE='$OLD_PROD_ROOT/env/prod.env' COMPOSE_PROJECT_NAME='$active_proj' bash backup.sh && echo PRE_MIGRATION_BACKUP_OK
    " || echo "警告：迁移前备份未成功（请确认是否需排查），继续停旧服并同步数据。" >&2
  fi

  # 2.3 停服切换窗口：停止旧 Caddy 与所有既有 Compose 栈（保留数据卷，不加 -v）
  echo "停止旧生产入口与既有容器栈..."
  systemctl stop shutong-caddy 2>/dev/null || true
  pkill -u "$dev_user" -f "caddy.*8180|caddy.*Caddyfile" 2>/dev/null || true
  for proj in "$active_proj" infra shutong-prod; do
    [[ -n "$proj" ]] || continue
    if [[ -f "$OLD_PROD_ROOT/repo/infra/compose.yaml" && -f "$OLD_PROD_ROOT/env/prod.env" ]]; then
      sudo -u "$PROD_USER" docker compose -p "$proj" --env-file "$OLD_PROD_ROOT/env/prod.env" \
        -f "$OLD_PROD_ROOT/repo/infra/compose.yaml" -f "$OLD_PROD_ROOT/repo/infra/compose.local.yaml" down 2>/dev/null || true
    fi
    # 兜底清理同名项目下仍在运行的容器（绝不删除数据卷）
    local cids
    cids="$(sudo -u "$PROD_USER" docker ps -aq --filter "label=com.docker.compose.project=$proj" 2>/dev/null || true)"
    if [[ -n "$cids" ]]; then
      sudo -u "$PROD_USER" docker rm -f $cids 2>/dev/null || true
    fi
  done
  # 兜底检查是否仍有旧容器占用 18000 端口
  local port_cids
  port_cids="$(sudo -u "$PROD_USER" docker ps -q --filter "publish=18000" 2>/dev/null || true)"
  if [[ -n "$port_cids" ]]; then
    sudo -u "$PROD_USER" docker rm -f $port_cids 2>/dev/null || true
  fi

  # 2.4 同步旧生产目录至 $PROD_HOME
  install -d -o "$PROD_USER" -g "$DEPLOY_GROUP" -m 710 "$PROD_HOME"
  rsync -aHAX "$OLD_PROD_ROOT/" "$PROD_HOME/"

  # 2.5 写入/校验 production/home.json
  cat > "$PROD_HOME/home.json" <<'EOF'
{
  "format_version": 1,
  "workspace_id": "pageboy-production",
  "environment": "production"
}
EOF
  chown "$PROD_USER:$PROD_USER" "$PROD_HOME/home.json"
  chmod 600 "$PROD_HOME/home.json"

  # 2.6 同步四科官方课标 PDF 原件至 production/data/curriculum_standards
  install -d -o "$PROD_USER" -g "$PROD_USER" -m 700 "$PROD_HOME/data/curriculum_standards"
  if [[ -d "$DEV_HOME/data/curriculum_standards" ]]; then
    rsync -a "$DEV_HOME/data/curriculum_standards/" "$PROD_HOME/data/curriculum_standards/"
  elif [[ -d "$REPO_ROOT/private-data/curriculum_standards" ]]; then
    rsync -a "$REPO_ROOT/private-data/curriculum_standards/" "$PROD_HOME/data/curriculum_standards/"
  fi

  # 2.7 严格收敛权限边界
  chown "$PROD_USER:$DEPLOY_GROUP" "$PROD_HOME"
  chmod 710 "$PROD_HOME"
  if [[ -d "$PROD_HOME/release.git" ]]; then
    chown -R "$PROD_USER:$DEPLOY_GROUP" "$PROD_HOME/release.git"
    chmod -R g+rwX "$PROD_HOME/release.git"
    find "$PROD_HOME/release.git" -type d -exec chmod g+s {} +
  fi
  for pdir in repo env data bin logs; do
    if [[ -d "$PROD_HOME/$pdir" ]]; then
      chown -R "$PROD_USER:$PROD_USER" "$PROD_HOME/$pdir"
    fi
  done
  chmod 750 "$PROD_HOME/repo" "$PROD_HOME/bin" "$PROD_HOME/logs"
  chmod 700 "$PROD_HOME/env" "$PROD_HOME/data" "$PROD_HOME/data/attachments" "$PROD_HOME/data/curriculum_standards"

  # 2.8 修复 prod.env 路径与运行 UID/GID
  local prod_uid prod_gid tmp_env
  prod_uid="$(id -u "$PROD_USER")"
  prod_gid="$(id -g "$PROD_USER")"
  tmp_env="$(mktemp)"
  sed "s|$OLD_PROD_ROOT|$PROD_HOME|g" "$PROD_HOME/env/prod.env" \
    | grep -v -E '^(PAGEBOY_HOME|SHUTONG_ENV|SHUTONG_UID|SHUTONG_GID|ATTACHMENTS_DIR|SHUTONG_ATTACHMENTS_DIR|SHUTONG_STANDARDS_DIR|RESTIC_PASSWORD_FILE)=' \
    > "$tmp_env"
  {
    echo "PAGEBOY_HOME=$HOME_ROOT"
    echo "SHUTONG_ENV=prod"
    echo "SHUTONG_UID=$prod_uid"
    echo "SHUTONG_GID=$prod_gid"
    echo "ATTACHMENTS_DIR=$PROD_HOME/data/attachments"
    echo "SHUTONG_ATTACHMENTS_DIR=$PROD_HOME/data/attachments"
    echo "SHUTONG_STANDARDS_DIR=$PROD_HOME/data/curriculum_standards"
    echo "RESTIC_PASSWORD_FILE=$PROD_HOME/env/restic-password"
  } >> "$tmp_env"
  mv "$tmp_env" "$PROD_HOME/env/prod.env"
  chown "$PROD_USER:$PROD_USER" "$PROD_HOME/env/prod.env"
  chmod 600 "$PROD_HOME/env/prod.env"
  if [[ -f "$PROD_HOME/env/restic-password" ]]; then
    chown "$PROD_USER:$PROD_USER" "$PROD_HOME/env/restic-password"
    chmod 600 "$PROD_HOME/env/restic-password"
  fi

  # 2.9 修复生产检出软链接与 Git safe.directory
  sudo -u "$PROD_USER" bash <<EOF
    set -e
    cd "$PROD_HOME/repo/infra"
    ln -sf "$PROD_HOME/env/prod.env" .env
    mkdir -p .local
    ln -sf "$PROD_HOME/bin/caddy" .local/caddy
    ln -sf "$PROD_HOME/bin/restic" .local/restic
    if [[ -d "$PROD_HOME/repo/.git" ]]; then
      git -C "$PROD_HOME/repo" remote set-url origin "$PROD_HOME/release.git" 2>/dev/null || true
    fi
EOF
  for dir in "$PROD_HOME/release.git"; do
    (cd / && sudo -u "$dev_user" git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$dir") \
      || (cd / && sudo -u "$dev_user" git config --global --add safe.directory "$dir")
  done
  for dir in "$PROD_HOME/release.git" "$PROD_HOME/repo"; do
    (cd / && sudo -u "$PROD_USER" git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$dir") \
      || (cd / && sudo -u "$PROD_USER" git config --global --add safe.directory "$dir")
  done

  # 2.10 拉起新路径生产容器栈
  local api_tag="dev"
  if [[ -f "$PROD_HOME/repo/infra/.local/deployed-tag" ]]; then
    api_tag="$(tr -d '[:space:]' < "$PROD_HOME/repo/infra/.local/deployed-tag")"
  fi
  echo "在新路径拉起生产容器栈 (SHUTONG_API_TAG=$api_tag, UID=$prod_uid)..."
  sudo -u "$PROD_USER" bash <<EOF
    set -e
    cd "$PROD_HOME/repo/infra"
    set -a; source "$PROD_HOME/env/prod.env"; set +a
    export SHUTONG_API_TAG="$api_tag"
    docker compose --env-file .env -f compose.yaml -f compose.local.yaml up -d db
    docker compose --env-file .env -f compose.yaml -f compose.local.yaml up -d api cloudflared
EOF

  # 2.11 更新并启动 Systemd Caddy 与 Crontab
  install -m 644 "$REPO_ROOT/infra/shutong-caddy.service" /etc/systemd/system/shutong-caddy.service
  systemctl daemon-reload
  systemctl enable shutong-caddy
  systemctl restart shutong-caddy

  sudo -u "$PROD_USER" crontab - <<EOF
0 */4 * * * cd $PROD_HOME/repo/infra && PATH=$PROD_HOME/bin:/usr/local/bin:/usr/bin:/bin bash backup.sh >> $PROD_HOME/logs/backup.log 2>&1
*/10 * * * * $PROD_HOME/repo/infra/tunnel-watchdog.sh
EOF

  # 2.12 等待健康探针就绪
  local ready=0
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:18000/health/ready >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 2
  done
  if [[ "$ready" -eq 1 ]]; then
    echo "✅ 生产容器 API 就绪: $(curl -fsS http://127.0.0.1:18000/health/live)"
  else
    echo "❌ 生产容器 API 就绪超时" >&2
    exit 1
  fi
  echo "✅ 宿主 Caddy 反代就绪: $(curl -fsS http://127.0.0.1:8180/health/live)"
  echo "✓ 生产环境已彻底迁入 $PROD_HOME（旧目录 $OLD_PROD_ROOT 暂保留作安全冷备）。"
}

case "$mode" in
  dev) setup_dev ;;
  prod) setup_prod ;;
  all)
    setup_dev
    setup_prod
    ;;
esac
