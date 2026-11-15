#!/usr/bin/env bash
# 开发/生产隔离自检（在开发用户下运行，只读）。任一项失败即退出码 1。
#   bash scripts/check_env_isolation.sh
set -uo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
home_root="${PAGEBOY_HOME:-/media/xc/backup_ext4/pageboy-home}"
dev_home="$home_root/development"
prod_home="$home_root/production"
fail=0
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; fail=1; }

# 1. 开发/生产 Home 目录结构与权限隔离
if [[ -d "$dev_home" && -f "$dev_home/home.json" ]]; then
  dev_perm="$(stat -c '%a:%U' "$dev_home")"
  if [[ "$dev_perm" == "700:$(id -un)" ]]; then
    ok "development Home 目录权限与属主正确 ($dev_perm)"
  else
    bad "development Home 目录权限或属主异常：$dev_perm（期望 700:$(id -un)）"
  fi
  if grep -q '"environment": "development"' "$dev_home/home.json" && grep -q '"workspace_id": "pageboy-development"' "$dev_home/home.json"; then
    ok "development home.json 身份有效"
  else
    bad "development home.json 身份内容异常"
  fi
else
  bad "缺少 development Home 目录或 home.json ($dev_home)"
fi

if [[ -f "$dev_home/env/dev.env" ]]; then
  dev_env_perm="$(stat -c '%a:%U' "$dev_home/env/dev.env")"
  if [[ "$dev_env_perm" == "600:$(id -un)" ]]; then
    ok "development dev.env 权限与属主正确 ($dev_env_perm)"
  else
    bad "development dev.env 权限或属主异常：$dev_env_perm（期望 600:$(id -un)）"
  fi
fi

if [[ -e "$HOME/.config/shutong" ]]; then
  bad "旧全局配置目录仍存在：$HOME/.config/shutong（应迁移至 \$PAGEBOY_HOME/<env>/k12100 并删除）"
else
  ok "旧全局配置目录已清除：$HOME/.config/shutong"
fi

if [[ -d "$dev_home/k12100" ]]; then
  dev_k12_perm="$(stat -c '%a:%U' "$dev_home/k12100")"
  if [[ "$dev_k12_perm" == "700:$(id -un)" ]]; then
    ok "development k12100 目录权限与属主正确 ($dev_k12_perm)"
  else
    bad "development k12100 目录权限或属主异常：$dev_k12_perm（期望 700:$(id -un)）"
  fi
  if [[ -f "$dev_home/k12100/k12100.env" ]]; then
    dev_k12_env_perm="$(stat -c '%a:%U' "$dev_home/k12100/k12100.env")"
    if [[ "$dev_k12_env_perm" == "600:$(id -un)" ]]; then
      ok "development k12100.env 权限与属主正确 ($dev_k12_env_perm)"
    else
      bad "development k12100.env 权限或属主异常：$dev_k12_env_perm（期望 600:$(id -un)）"
    fi
  fi
fi

if [[ -d "$prod_home" ]]; then
  prod_perm="$(stat -c '%a:%U:%G' "$prod_home")"
  if [[ "$prod_perm" == "710:shutong-prod:shutong-deploy" ]]; then
    ok "production Home 目录权限与属主正确 ($prod_perm)"
  else
    bad "production Home 目录权限或属主异常：$prod_perm（期望 710:shutong-prod:shutong-deploy）"
  fi
else
  bad "缺少 production Home 目录 ($prod_home)"
fi

# 2. 开发用户绝对不可读生产机密、数据与工作树
for forbidden in \
  "$prod_home/env/prod.env" \
  "$prod_home/env/restic-password" \
  "$prod_home/data" \
  "$prod_home/repo" \
  "$prod_home/home.json" \
  "/media/xc/backup_ext4/prod-env/pageboy/env/prod.env" \
  "/srv/shutong/env/prod.env"; do
  if [[ -r "$forbidden" ]]; then
    bad "开发用户可读生产受保护路径：$forbidden"
  else
    ok "开发用户不可读：$forbidden"
  fi
done

# 3. 开发用户不在系统 docker 组（docker 组等同 root，可读生产卷）
if id -nG "${USER:-$(id -un)}" | tr ' ' '\n' | grep -qx docker; then
  bad "开发用户仍在 docker 组"
else
  ok "开发用户不在 docker 组"
fi

# 4. 代码仓库内严禁残留数据库、机密、附件、课标原件或本地运行状态
for f in \
  infra/.env \
  infra/.local \
  private-data \
  services/api/private-data \
  services/api/shutong-dev.sqlite3 \
  apps/web/shutong-dev.sqlite3; do
  if [[ -e "$repo_root/$f" ]]; then
    bad "代码仓库残留运行时文件/目录：$f"
  else
    ok "代码仓库无残留：$f"
  fi
done

# 5. 开发/测试服务端口只能监听回环地址；生产入口 8180 不可由开发用户进程占用
for port in 18765 4173 5173 8000; do
  listen="$(ss -ltnH "sport = :$port" 2>/dev/null | awk '{print $4}')"
  if [[ -z "$listen" ]]; then ok "端口 $port 未监听"
  elif grep -qvE '^(127\.0\.0\.1|\[::1\]):' <<<"$listen"; then bad "端口 $port 监听非回环地址：$listen"
  else ok "端口 $port 仅回环"; fi
done

if pgrep -u "$(id -un)" -x caddy >/dev/null 2>&1; then
  bad "发现开发用户下残留 Caddy 进程"
else
  ok "无开发用户残留 Caddy 进程"
fi

exit "$fail"
