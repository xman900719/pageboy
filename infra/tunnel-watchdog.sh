#!/usr/bin/env bash
# 隧道自愈（ST-016/OPS 后续）：本机网络对 Cloudflare edge 的 TLS 握手会间歇性超时
# （实测 cloudflared 反复 "Serve tunnel error"/"no free edge addresses"，曾导致线上
# 持续 1033 而 Access 层 302 正常——普通探检查不出）。判据（保守，带冷却）：
#   近 15 分钟日志出现 edge 连接错误，且同一窗口无任何 "Registered tunnel connection"
#   → 视为隧道已断，重建 cloudflared 容器（2026-10-30 实测该动作可恢复）。
# 不降级 schema、不触碰 db/api/附件；最坏情况是一次 api 之外的无害容器重建。
set -uo pipefail

INFRA="$(cd "$(dirname "$0")" && pwd)"  # 随脚本所在检出目录，不绑定开发路径
ENV_FILE="${ENV_FILE:-.env}"
compose() { ( cd "$INFRA" && docker compose --env-file "$ENV_FILE" -f compose.yaml -f compose.local.yaml "$@" ); }
LOG_DIR="$INFRA/.local/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/shutong-tunnel-watchdog.log"
STATE="$LOG_DIR/shutong-tunnel-watchdog.state"

stamp() { date -u +%FT%TZ; }

# 冷却：距上次重建不足 15 分钟则跳过（避免风暴）。
if [[ -f "$STATE" ]]; then
  last=$(stat -c %Y "$STATE" 2>/dev/null || echo 0)
  now=$(date +%s)
  (( now - last < 900 )) && exit 0
fi

cid=$(compose ps -q cloudflared 2>/dev/null)
window=$([[ -n "$cid" ]] && docker logs --since 15m "$cid" 2>&1 | tail -200)
if grep -q "Registered tunnel connection" <<<"$window"; then
  exit 0  # 窗口内有成功注册：隧道活着。
fi
if ! grep -qE "Unable to establish connection with Cloudflare edge|Serve tunnel error|no free edge addresses left" <<<"$window"; then
  exit 0  # 既无错误也无注册（长期稳定连接不重日志）：视为健康。
fi

echo "$(stamp) tunnel unhealthy (edge errors, no registration in 15m) -> recreate" >> "$LOG"
compose up -d --no-deps --force-recreate cloudflared >> "$LOG" 2>&1
touch "$STATE"
echo "$(stamp) recreated cloudflared" >> "$LOG"
