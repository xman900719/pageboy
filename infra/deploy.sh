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
#   C5: --allow-dirty 已禁用；构建必须来自干净提交。
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
    --allow-dirty) echo 'REFUSED: C5 requires a clean committed build source' >&2; exit 3 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# 环境隔离护栏：标签取自 git HEAD，有未提交改动时镜像内容与标签不符，默认拒绝。
if [[ "$allow_dirty" -eq 0 && -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "工作区有未提交改动，拒绝部署（标签 $(git -C "$repo_root" rev-parse --short HEAD) 将不可追溯）；C5 不允许脏工作区" >&2
  exit 3
fi

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:18000}"
WEB_BASE_URL="${WEB_BASE_URL:-http://127.0.0.1:8180}"
STATE_DIR="$here/.local"
PREVIOUS_TAG_FILE="$STATE_DIR/previous-tag"
DEPLOYED_TAG_FILE="$STATE_DIR/deployed-tag"
mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/artifact.lock"
flock -x 9
helper="$repo_root/scripts/web_artifact_provenance.py"
full_sha="$(git -C "$repo_root" rev-parse HEAD)"

compose() { docker compose --env-file "$ENV_FILE" -f compose.yaml -f compose.local.yaml "$@"; }

current_tag="$(cat "$DEPLOYED_TAG_FILE" 2>/dev/null || true)"
build_tag="${SHUTONG_API_TAG:-}"
if [[ -z "$build_tag" ]]; then
  build_tag="api-$(git -C "$repo_root" rev-parse --short HEAD)"
fi
# Compose resolves image: from the environment for build AND run, not only up.
if [[ -n "${EXPECTED_RELEASE_SHA:-}" ]]; then
  [[ "$(git -C "$repo_root" rev-parse HEAD)" == "$EXPECTED_RELEASE_SHA" &&
     "$build_tag" == "api-$(git -C "$repo_root" rev-parse --short HEAD)" ]] || {
    echo 'REFUSED: release SHA or image tag mismatch' >&2; exit 1;
  }
fi
[[ "$full_sha" =~ ^[0-9a-f]{40}$ && "$build_tag" == api-$(git -C "$repo_root" rev-parse --short HEAD) ]] || { echo 'REFUSED: build tag must match clean HEAD' >&2; exit 1; }
export SHUTONG_API_TAG="$build_tag"

smoke() {
  local tag="$1"
  local live ready subjects admin_check graph_check web
  local admin_tok="${SHUTONG_ADMIN_TOKEN:-${SHUTONG_TOKEN:-}}"
  local student_tok="${SHUTONG_STUDENT_TOKEN:-}"
  [[ -n "$admin_tok" ]] || { echo "SMOKE FAIL: missing SHUTONG_ADMIN_TOKEN / SHUTONG_TOKEN" >&2; return 1; }
  [[ -n "$student_tok" ]] || { echo "SMOKE FAIL: missing SHUTONG_STUDENT_TOKEN" >&2; return 1; }
  live="$(curl -fsS --max-time 10 "$API_BASE_URL/health/live")"
  ready="$(curl -fsS --max-time 10 "$API_BASE_URL/health/ready")"
  # app_revision 与镜像标签一致，才承认"这个构建在服务"（ST-017）。
  grep -q "\"app_revision\":\"$tag\"" <<<"$live" || { echo "SMOKE FAIL: /health/live 未报告 $tag：$live" >&2; return 1; }
  grep -q '"env":"prod"' <<<"$live" || { echo "SMOKE FAIL: /health/live 未报告 env=prod：$live" >&2; return 1; }
  grep -q '"status":"ready"' <<<"$ready" || { echo "SMOKE FAIL: /health/ready: $ready" >&2; return 1; }
  admin_check="$(curl -fsS --max-time 10 -H "Authorization: Bearer $admin_tok" "$API_BASE_URL/api/admin/verify")"
  grep -q '"role":"admin"' <<<"$admin_check" || { echo "SMOKE FAIL: /api/admin/verify: $admin_check" >&2; return 1; }
  subjects="$(curl -fsS --max-time 10 -H "Authorization: Bearer $student_tok" "$API_BASE_URL/api/subjects")"
  grep -q '"math"' <<<"$subjects" || { echo "SMOKE FAIL: /api/subjects: $subjects" >&2; return 1; }
  graph_check="$(curl -fsS --max-time 10 -H "Authorization: Bearer $student_tok" "$API_BASE_URL/api/knowledge/graph?subject=math")"
  grep -q '"nodes"' <<<"$graph_check" || { echo "SMOKE FAIL: /api/knowledge/graph: $graph_check" >&2; return 1; }
  web="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 "$WEB_BASE_URL/")"
  [[ "$web" == "200" ]] || { echo "SMOKE FAIL: web root HTTP $web" >&2; return 1; }
  echo "SMOKE OK ($tag): live+ready+admin+subjects+graph+web"
}

wait_healthy() {
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 5 "$API_BASE_URL/health/ready" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  echo "api 未在 60s 内就绪" >&2
  return 1
}

if [[ "$no_build" == "0" ]]; then
  echo "== build API from committed source =="
  build_context="$(mktemp -d "$STATE_DIR/.c5-api.XXXXXX")"
  trap 'rm -rf "$build_context"' EXIT
  python3 "$helper" export "$repo_root" "$full_sha" "$build_context"
  docker build --build-arg "SHUTONG_GIT_SHA=$full_sha" -t "shutong-api:$build_tag" -f "$build_context/infra/Dockerfile.api" "$build_context"
fi
image_id="$(docker image inspect --format '{{.Id}}' "shutong-api:$build_tag")"
label="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_id")"
[[ "$label" == "$full_sha" && "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'REFUSED: API build provenance mismatch' >&2; exit 1; }
if [[ "$with_web" == "1" ]]; then
  python3 "$helper" build "$repo_root" "$STATE_DIR"
fi
[[ "$(git -C "$repo_root" rev-parse HEAD)" == "$full_sha" && -z "$(git -C "$repo_root" status --porcelain)" ]] || { echo 'REFUSED: source changed' >&2; exit 1; }

echo "== migrate to head（同镜像一次性容器；幂等） =="
compose run --rm -e SHUTONG_APP_REVISION="$build_tag" api alembic upgrade head

echo "== replace api service =="
SHUTONG_API_TAG="$build_tag" compose up -d --no-deps api
wait_healthy
smoke "$build_tag"
cid="$(compose ps -q api)"
[[ "$cid" =~ ^[0-9a-f]{12,64}$ ]] || { echo 'REFUSED: ambiguous API container' >&2; exit 1; }
[[ "$(docker inspect --format '{{.Image}}' "$cid")" == "$image_id" && "$(docker inspect --format '{{.Config.Image}}' "$cid")" == "shutong-api:$build_tag" ]] || { echo 'REFUSED: deployed API image mismatch' >&2; exit 1; }

if [[ -n "$current_tag" && "$current_tag" != "$build_tag" ]]; then
  printf '%s\n' "$current_tag" > "$PREVIOUS_TAG_FILE"
  echo "上一个可用标签已记录：$current_tag（回滚：infra/rollback.sh $current_tag）"
fi
printf '%s\n' "$build_tag" > "$DEPLOYED_TAG_FILE"
echo "部署完成：shutong-api:$build_tag"
