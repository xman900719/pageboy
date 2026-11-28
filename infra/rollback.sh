#!/usr/bin/env bash
# ROLLBACK（本机生产栈）：把 api 服务切回上一个已记录（或显式指定）的本地镜像标签。
#
# 红线（与 deploy.sh 一致）：
#   * 只切镜像；不降级 schema。结构回滚是数据决策，必须人工 + 独立备份确认（recovery-runbook.md）。
#   * 目标镜像必须仍在本地（deploy.sh 刻意不做 docker image prune）；缺失即中止，不联网硬拉。
#   * 切回后执行与部署完全相同的健康/冒烟校验，以 /health/live 的 app_revision 证明显效。
#
# 用法：
#   infra/rollback.sh                 # 回滚到 infra/.local/previous-tag 记录的标签
#   infra/rollback.sh api-1a2b3c4     # 显式回滚到指定标签
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
ENV_FILE="${ENV_FILE:-.env}"
[[ -f "$ENV_FILE" ]] || { echo "missing env file: $ENV_FILE" >&2; exit 1; }
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:18000}"
WEB_BASE_URL="${WEB_BASE_URL:-http://127.0.0.1:8180}"
STATE_DIR="$here/.local"
PREVIOUS_TAG_FILE="$STATE_DIR/previous-tag"
DEPLOYED_TAG_FILE="$STATE_DIR/deployed-tag"
mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/artifact.lock"
flock -x 9

target="${1:-$(cat "$PREVIOUS_TAG_FILE" 2>/dev/null || true)}"
[[ -n "$target" ]] || { echo "未指定标签且无 previous-tag 记录；用法：infra/rollback.sh <tag>" >&2; exit 2; }
docker image inspect "shutong-api:$target" >/dev/null 2>&1 || { echo "本地不存在 shutong-api:$target（已被清理或不曾部署）；不从远端硬拉" >&2; exit 1; }

compose() { docker compose --env-file "$ENV_FILE" -f compose.yaml -f compose.local.yaml "$@"; }

echo "== rollback api → shutong-api:$target =="
SHUTONG_API_TAG="$target" compose up -d --no-deps api

for _ in $(seq 1 30); do
  curl -fsS --max-time 5 "$API_BASE_URL/health/ready" >/dev/null 2>&1 && break
  sleep 2
done
live="$(curl -fsS --max-time 10 "$API_BASE_URL/health/live")"
grep -q "\"app_revision\":\"$target\"" <<<"$live" || { echo "ROLLBACK FAIL: /health/live 未报告 $target：$live" >&2; exit 1; }
curl -fsS --max-time 10 "$API_BASE_URL/health/ready" | grep -q '"status":"ready"' || { echo "ROLLBACK FAIL: /health/ready" >&2; exit 1; }
curl -fsS --max-time 10 -H "Authorization: Bearer $SHUTONG_TOKEN" "$API_BASE_URL/api/subjects" | grep -q '"math"' || { echo "ROLLBACK FAIL: /api/subjects" >&2; exit 1; }
[[ "$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 "$WEB_BASE_URL/")" == "200" ]] || { echo "ROLLBACK FAIL: web root" >&2; exit 1; }

printf '%s\n' "$target" > "$DEPLOYED_TAG_FILE"
echo "回滚生效：shutong-api:$target（live+ready+subjects+web 全过）"
echo "注意：schema 未降级；若该版本需要旧结构，按 docs/operations/recovery-runbook.md 人工决策。"
