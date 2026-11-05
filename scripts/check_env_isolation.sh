#!/usr/bin/env bash
# 开发/生产隔离自检（在开发用户下运行，只读）。任一项失败即退出码 1。
#   bash scripts/check_env_isolation.sh
set -uo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; fail=1; }

# 1. 开发用户读不到生产机密
prod_env="${SHUTONG_PROD_ENV:-/media/xc/backup_ext4/prod-env/pageboy/env/prod.env}"
if [[ -r "$prod_env" ]] || [[ -r /srv/shutong/env/prod.env ]]; then
  bad "开发用户可读生产 prod.env"
else
  ok "开发用户不可读生产 prod.env"
fi

# 2. 开发用户不在系统 docker 组（docker 组等同 root，可读生产卷）
if id -nG "${USER:-$(id -un)}" | tr ' ' '\n' | grep -qx docker; then bad "开发用户仍在 docker 组"; else ok "开发用户不在 docker 组"; fi

# 3. 开发树内不得残留生产机密/真实附件
for f in infra/.env infra/.local/restic-password; do
  if [[ -e "$repo_root/$f" ]]; then bad "开发树残留 $f"; else ok "开发树无 $f"; fi
done
if [[ -n "$(find "$repo_root/infra/private-data/attachments" -type f 2>/dev/null | head -1)" ]]; then
  bad "开发树 infra/private-data/attachments 仍有真实附件"
else ok "开发树无真实附件"; fi

# 4. 开发/测试服务端口只能监听回环地址（iPad 只连生产）
for port in 18765 4173 5173 8000; do
  listen="$(ss -ltnH "sport = :$port" 2>/dev/null | awk '{print $4}')"
  if [[ -z "$listen" ]]; then ok "端口 $port 未监听"
  elif grep -qvE '^(127\.0\.0\.1|\[::1\]):' <<<"$listen"; then bad "端口 $port 监听非回环地址：$listen"
  else ok "端口 $port 仅回环"; fi
done

exit "$fail"
