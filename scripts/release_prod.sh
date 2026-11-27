#!/usr/bin/env bash
# 一键生产发布与验证脚本（在开发用户 xc 下执行；保留 xc ↔ shutong-prod 双用户安全隔离）。
#
# 三阶段流程：
#   阶段 A（开发用户 xc）：分支/工作区/隔离预检 → 推送 release.git
#   阶段 B（单次 sudo -iu shutong-prod）：env 与课标预检 → R2 联合备份 → git pull → deploy.sh --web → alembic/taxonomy_audit
#   阶段 C（退回开发用户 xc）：线上环回探针（app_revision/ready/静态资源/CF-Ray 403）与环境隔离复检
#
# 用法：
#   bash scripts/release_prod.sh --approve-sha=<完整SHA>  # 正式发布必须有独立授权
#   bash scripts/release_prod.sh --dry-run   # 仅执行开发侧预检、打印发布命令并探测当前线上状态
#   bash scripts/release_prod.sh --approve-sha=<完整SHA>
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
pageboy_home="${PAGEBOY_HOME:-/media/xc/backup_ext4/pageboy-home}"
prod_home="${PROD_HOME:-$pageboy_home/production}"
release_git="$prod_home/release.git"
web_base_url="${WEB_BASE_URL:-http://127.0.0.1:8180}"

dry_run=0
approved_sha=""

usage() {
  cat <<'EOF'
用法：bash scripts/release_prod.sh [选项]

选项：
  --dry-run         仅执行开发侧只读预检、打印三阶段计划并查看当前线上状态，不执行 push 或 sudo 部署
  --approve-sha=SHA  正式发布必须显式确认完整 40 位已通过 CI 的 main SHA
  -h, --help        显示帮助
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    --approve-sha=*) approved_sha="${arg#*=}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$arg" >&2; usage >&2; exit 2 ;;
  esac
done

log()  { printf '\n==> %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

verify_prod_http() {
  local expected_rev="$1"
  local live ready student_code admin_code cfray_code index_html admin_html main_js admin_js
  live="$(curl -fsS --max-time 10 "$web_base_url/health/live")"
  ready="$(curl -fsS --max-time 10 "$web_base_url/health/ready")"
  echo "health/live : $live"
  echo "health/ready: $ready"
  grep -q '"env":"prod"' <<<"$live" || fail "/health/live 未报告 env=prod：$live"
  if [[ -n "$expected_rev" ]]; then
    grep -q "\"app_revision\":\"$expected_rev\"" <<<"$live" || fail "/health/live 未报告 $expected_rev：$live"
  fi
  grep -q '"status":"ready"' <<<"$ready" || fail "/health/ready 未就绪：$ready"

  student_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$web_base_url/")"
  admin_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$web_base_url/admin.html")"
  cfray_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H "CF-Ray: simulated-edge" "$web_base_url/admin.html")"
  echo "HTTP 状态：student=$student_code, admin_local=$admin_code, admin_cfray=$cfray_code"
  [[ "$student_code" == "200" ]] || fail "学生端首页返回 HTTP $student_code（期望 200）"
  [[ "$admin_code" == "200" ]] || fail "管理端本地入口返回 HTTP $admin_code（期望 200）"
  [[ "$cfray_code" == "403" ]] || fail "外网 CF-Ray 访问 /admin.html 返回 HTTP $cfray_code（期望 403）"

  index_html="$(curl -fsS --max-time 10 "$web_base_url/")"
  admin_html="$(curl -fsS --max-time 10 "$web_base_url/admin.html")"
  main_js="$(grep -oE '/assets/main-[^"]+\.js' <<<"$index_html" | head -n1 || true)"
  admin_js="$(grep -oE '/assets/admin-[^"]+\.js' <<<"$admin_html" | head -n1 || true)"
  [[ -n "$main_js" ]] || fail "未能从学生端 HTML 提取 /assets/main-*.js"
  [[ -n "$admin_js" ]] || fail "未能从管理端 HTML 提取 /assets/admin-*.js"
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$web_base_url$main_js")" == "200" ]] || fail "静态资源不可达：$main_js"
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$web_base_url$admin_js")" == "200" ]] || fail "静态资源不可达：$admin_js"
  echo "静态入口资源：main=$main_js (200), admin=$admin_js (200)"
}

# 禁止在 root 或 shutong-prod 下直接运行开发侧脚本
current_user="$(id -un)"
[[ "$current_user" != "root" && "$current_user" != "shutong-prod" ]] || \
  fail "请使用开发用户（xc）在开发仓库运行本脚本，切勿以 $current_user 直接运行"

log "阶段 A · 开发侧预检 ($repo_root)"
[[ -z "$(git -C "$repo_root" status --porcelain)" ]] || fail "工作区存在未提交改动，拒绝发布"

branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
[[ "$branch" == main ]] || fail "仅允许发布 main"
target_sha="$(git -C "$repo_root" rev-parse HEAD)"
target_rev="$(git -C "$repo_root" rev-parse --short HEAD)"
remote_sha="$(git -C "$repo_root" ls-remote --exit-code origin refs/heads/main | cut -f1)"
[[ "$target_sha" == "$remote_sha" ]] || fail "本地 HEAD 不是远端 main 当前 SHA"
if [[ "$dry_run" -eq 0 ]]; then
  [[ "$approved_sha" == "$target_sha" ]] || fail "正式发布须传 --approve-sha=$target_sha"
fi
python3 "$repo_root/scripts/check_release_ci.py" "$target_sha"
echo "发布目标：$branch @ $target_rev ($target_sha)"

bash "$repo_root/scripts/check_env_isolation.sh"

if [[ "$dry_run" -eq 1 ]]; then
  log "DRY-RUN · 将执行的发布计划"
  cat <<EOF
1. [xc]       git -C "$repo_root" push "$release_git" HEAD:refs/heads/release
2. [shutong-prod] 校验 prod.env 与四科 2022 课标 PDF 目录
3. [shutong-prod] fetch release + 核对 SHA + fast-forward（不启动服务）
4. [shutong-prod] ENV_FILE="$prod_home/env/prod.env" bash infra/backup.sh（必须返回确认快照 ID）
5. [shutong-prod] ENV_FILE="$prod_home/env/prod.env" infra/deploy.sh --web
6. [shutong-prod] alembic current + python -m shutong.taxonomy_audit
7. [xc]       校验 $web_base_url (/health/live == api-$target_rev, ready, 静态资源, CF-Ray 403) + check_env_isolation.sh
EOF
  log "DRY-RUN · 当前线上只读状态"
  verify_prod_http ""
  echo "DRY_RUN_OK: 当前本地基线为 api-$target_rev"
  exit 0
fi

log "阶段 A · 推送单向发布仓库 ($release_git)"
git -C "$repo_root" push "$release_git" HEAD:refs/heads/release

log "阶段 B · 切入 shutong-prod 执行 R2 备份、部署与知识体系核对"
# 通过命令行参数传入脚本，保持 stdin 连接 TTY 以便 sudo 正常提示输入口令
sudo -iu shutong-prod bash -ceu '
  prod_home="$1"
  expected_sha="$2"
  expected_rev="$3"
  prod_repo="$prod_home/repo"
  prod_env="$prod_home/env/prod.env"
  standards_dir="$prod_home/data/curriculum_standards"

  [[ -d "$prod_repo" ]] || { echo "缺少生产仓库：$prod_repo" >&2; exit 1; }
  [[ -f "$prod_env" ]] || { echo "缺少生产配置：$prod_env" >&2; exit 1; }

  set -a; source "$prod_env"; set +a
  [[ -n "${SHUTONG_ADMIN_TOKEN:-}" ]] || { echo "prod.env 缺少 SHUTONG_ADMIN_TOKEN" >&2; exit 1; }
  [[ -n "${SHUTONG_STUDENT_TOKEN:-}" ]] || { echo "prod.env 缺少 SHUTONG_STUDENT_TOKEN" >&2; exit 1; }
  [[ "$SHUTONG_ADMIN_TOKEN" != "$SHUTONG_STUDENT_TOKEN" ]] || { echo "SHUTONG_ADMIN_TOKEN 与 SHUTONG_STUDENT_TOKEN 不可相同" >&2; exit 1; }
  [[ -n "${SHUTONG_AI_API_KEY:-}" ]] || { echo "prod.env 缺少 SHUTONG_AI_API_KEY" >&2; exit 1; }
  [[ -n "${SHUTONG_TUNNEL_TOKEN:-}" ]] || { echo "prod.env 缺少 SHUTONG_TUNNEL_TOKEN" >&2; exit 1; }
  pdf_count="$(find "$standards_dir" -maxdepth 2 -type f -name "*.pdf" 2>/dev/null | wc -l | tr -d " ")"
  [[ "$pdf_count" -ge 4 ]] || { echo "课标原件目录 PDF 数量异常（$pdf_count < 4）：$standards_dir" >&2; exit 1; }

  cd "$prod_repo"
  echo "-- 1/4 fetch release 并核对 SHA（不更新运行中的服务） --"
  [[ -z "$(git status --porcelain)" ]] || { echo "生产工作树不干净" >&2; exit 1; }
  git fetch origin release
  [[ "$(git rev-parse FETCH_HEAD)" == "$expected_sha" ]] || { echo "release SHA 不符" >&2; exit 1; }
  git merge --ff-only "$expected_sha"
  [[ "$(git rev-parse HEAD)" == "$expected_sha" ]] || exit 1

  echo "-- 2/4 升级前使用新脚本执行 R2 联合备份 --"
  [[ -z "${BACKUP_OUTPUT_DIR:-}" ]] || { echo "禁止本地演练备份作为生产发布门禁" >&2; exit 1; }
  backup_result="$(ENV_FILE="$prod_env" bash infra/backup.sh)"
  printf "%s\n" "$backup_result"
  grep -Eq "^BACKUP_SNAPSHOT_OK=[0-9a-f]{8,64}$" <<<"$backup_result" || { echo "无已确认的异地快照 ID，停止发布" >&2; exit 1; }

  echo "-- 3/4 执行前端构建、镜像构建、迁移与容器替换 --"
  EXPECTED_RELEASE_SHA="$expected_sha" SHUTONG_API_TAG="api-$expected_rev" ENV_FILE="$prod_env" bash infra/deploy.sh --web

  echo "-- 4/4 核对 Alembic 当前版本与四科 v2022.1.0 知识体系 --"
  docker compose --env-file "$prod_env" -f infra/compose.yaml -f infra/compose.local.yaml exec -T api alembic current
  docker compose --env-file "$prod_env" -f infra/compose.yaml -f infra/compose.local.yaml exec -T api python -m shutong.taxonomy_audit
' _ "$prod_home" "$target_sha" "$target_rev"

log "阶段 C · 退回开发用户 xc 执行线上只读终验"
verify_prod_http "api-$target_rev"
bash "$repo_root/scripts/check_env_isolation.sh"

printf '\nRELEASE_OK: api-%s (%s) 已完成备份、部署与全项线上验收。\n' "$target_rev" "$target_sha"
