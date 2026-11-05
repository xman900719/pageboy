#!/usr/bin/env bash
# DEPLOY（本机生产栈，compose.local override）：构建带 git 标签的 API 镜像 → 迁移到 head →
# 原子替换 api 服务 → 健康/冒烟校验 → 记录上一个可用标签供回滚。
#
# 设计红线（与 docs/operations/deployment.md、recovery-runbook.md 一致）：
#   * 只替换 api 服务镜像；db 卷与附件 bind mount 不触碰（数据不在本脚本处置范围内）。
#   * 迁移用同镜像一次性执行 `alembic upgrade head`（幂等；head 已达成时为无操作）。
#   -schema 降级永远不在本脚本或 rollback.sh 中执行：真实结构回滚须人工决策 + 独立备份确认。
#   * SHUTONG_APP_REVISION 透传镜像标签，/health/live 因此能证明"哪个构建在服务"。
#
# 用法：
#   infra/deploy.sh                 # 构建并部署 shutong-api:api-<git短SHA>
#   SHUTONG_API_TAG=api-<sha> infra/deploy.sh --no-build   # 只切换/重部署已有本地镜像
#   infra/deploy.sh --web           # 部署前先重建 apps/web/dist（宿主 caddy 直接伺服）
#   infra/deploy.sh --allow-dirty   # 工作区有未提交改动时默认拒绝部署；显式放行（标签将不可追溯）
#
# 环境：infra/.env（与运行栈同一份；不新建、不打印其中的机密）。
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
repo_root="$(cd .. && pwd)"
ENV_FILE="${ENV_FILE:-.env}"
[[ -f "$ENV_FILE" ]] || { echo "missing env file: $ENV_FILE" >&2; exit 1; }
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a

no_build=0
with_web=0
allow_dirty=0
for arg in "$@"; do
  case "$arg" in
    --no-build) no_build=1 ;;
    --web) with_web=1 ;;
    --allow-dirty) allow_dirty=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# 环境隔离护栏：标签取自 git HEAD，有未提交改动时镜像内容与标签不符，默认拒绝。
if [[ "$allow_dirty" -eq 0 && -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "工作区有未提交改动，拒绝部署（标签 $(git -C "$repo_root" rev-parse --short HEAD) 将不可追溯）；确需部署请加 --allow-dirty" >&2
  exit 3
fi

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:18000}"
WEB_BASE_URL="${WEB_BASE_URL:-http://127.0.0.1:8180}"
STATE_DIR="$here/.local"
PREVIOUS_TAG_FILE="$STATE_DIR/previous-tag"
DEPLOYED_TAG_FILE="$STATE_DIR/deployed-tag"
mkdir -p "$STATE_DIR"

compose() { docker compose --env-file "$ENV_FILE" -f compose.yaml -f compose.local.yaml "$@"; }

current_tag="$(cat "$DEPLOYED_TAG_FILE" 2>/dev/null || true)"
build_tag="${SHUTONG_API_TAG:-}"
if [[ -z "$build_tag" ]]; then
  build_tag="api-$(git -C "$repo_root" rev-parse --short HEAD)"
fi

smoke() {
  local tag="$1"
  local live ready subjects web
  live="$(curl -fsS --max-time 10 "$API_BASE_URL/health/live")"
  ready="$(curl -fsS --max-time 10 "$API_BASE_URL/health/ready")"
  # app_revision 与镜像标签一致，才承认"这个构建在服务"（ST-017）。
  grep -q "\"app_revision\":\"$tag\"" <<<"$live" || { echo "SMOKE FAIL: /health/live 未报告 $tag：$live" >&2; return 1; }
  grep -q '"env":"prod"' <<<"$live" || { echo "SMOKE FAIL: /health/live 未报告 env=prod：$live" >&2; return 1; }
  grep -q '"status":"ready"' <<<"$ready" || { echo "SMOKE FAIL: /health/ready: $ready" >&2; return 1; }
  subjects="$(curl -fsS --max-time 10 -H "Authorization: Bearer $SHUTONG_TOKEN" "$API_BASE_URL/api/subjects")"
  grep -q '"math"' <<<"$subjects" || { echo "SMOKE FAIL: /api/subjects: $subjects" >&2; return 1; }
  web="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 "$WEB_BASE_URL/")"
  [[ "$web" == "200" ]] || { echo "SMOKE FAIL: web root HTTP $web" >&2; return 1; }
  echo "SMOKE OK ($tag): live+ready+subjects+web"
}

wait_healthy() {
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 5 "$API_BASE_URL/health/ready" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  echo "api 未在 60s 内就绪" >&2
  return 1
}

if [[ "$with_web" == "1" ]]; then
  echo "== rebuild web dist =="
  (cd "$repo_root/apps/web" && npm ci --no-audit --no-fund && npm run build)
fi

if [[ "$no_build" == "0" ]]; then
  echo "== build shutong-api:$build_tag =="
  # compose.yaml 的 image: 命名保证构建产物即 shutong-api:$build_tag（不依赖项目名间接标签）。
  compose build api
else
  docker image inspect "shutong-api:$build_tag" >/dev/null || { echo "本地不存在镜像 shutong-api:$build_tag" >&2; exit 1; }
fi

echo "== migrate to head（同镜像一次性容器；幂等） =="
compose run --rm -e SHUTONG_APP_REVISION="$build_tag" api alembic upgrade head

echo "== replace api service =="
SHUTONG_API_TAG="$build_tag" compose up -d --no-deps api
wait_healthy
smoke "$build_tag"

if [[ -n "$current_tag" && "$current_tag" != "$build_tag" ]]; then
  printf '%s\n' "$current_tag" > "$PREVIOUS_TAG_FILE"
  echo "上一个可用标签已记录：$current_tag（回滚：infra/rollback.sh $current_tag）"
fi
printf '%s\n' "$build_tag" > "$DEPLOYED_TAG_FILE"
echo "部署完成：shutong-api:$build_tag"
