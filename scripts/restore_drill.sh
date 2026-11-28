#!/usr/bin/env bash
# 一键隔离恢复演练脚本（只读 R2 异地仓库快照，在独立临时容器与 /tmp 目录验证，不触碰生产）
#
# 用法：
#   bash scripts/restore_drill.sh
#   SNAPSHOT_ID=<id> bash scripts/restore_drill.sh  # 指定快照 ID（默认 latest）
#
# 依赖：docker、restic、python3、.venv（带 shutong 依赖）
set -euo pipefail
# Temporary C1/C2 quarantine; C3 must implement explicit read-only R2 approval.
echo "REFUSED: R2 restore disabled pending ST-024-C3 isolated target and authorization" >&2
exit 1

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra"
ENV_FILE="${ENV_FILE:-$INFRA_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ 缺少环境配置文件: $ENV_FILE" >&2
  exit 1
fi

# 加载配置（用于 restic 仓库连接凭据与密码文件）
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a

: "${RESTIC_REPOSITORY:?需要设置 RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD_FILE:?需要设置 RESTIC_PASSWORD_FILE}"

command -v restic >/dev/null || { echo "❌ 未找到 restic 命令" >&2; exit 1; }
command -v docker >/dev/null || { echo "❌ 未找到 docker 命令" >&2; exit 1; }

SNAPSHOT_TARGET="${SNAPSHOT_ID:-latest}"
DRILL_DIR="$(mktemp -d /tmp/shutong-drill.XXXXXX)"
CONTAINER_NAME="pageboy-drill-pg-$(date +%s)"
DRILL_PORT=55432
DRILL_DB="pageboy_drill"
DRILL_USER="drill"
DRILL_PASS="drill_secret_123"

cleanup() {
  local exit_code=$?
  echo "🧹 正在清理隔离演练临时资源..."
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  rm -rf "$DRILL_DIR" || true
  if [[ $exit_code -eq 0 ]]; then
    echo "✅ 演练完成且临时资源已清理干净。"
  else
    echo "⚠️ 演练未正常完成或失败，临时资源已清理。"
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

chmod 700 "$DRILL_DIR"
echo "==> 1. 查看并拉取快照 ($SNAPSHOT_TARGET)..."
mkdir -p "$DRILL_DIR/restic" "$DRILL_DIR/attachments"

restic restore "$SNAPSHOT_TARGET" --tag shutong-foundation --target "$DRILL_DIR/restic"

BACKUP_DIR="$(dirname "$(find "$DRILL_DIR/restic" -name SHA256SUMS | head -1)")"
if [[ -z "$BACKUP_DIR" || ! -f "$BACKUP_DIR/SHA256SUMS" ]]; then
  echo "❌ 未能在恢复产物中找到 SHA256SUMS" >&2
  exit 1
fi

echo "==> 2. 快照元信息清单："
cat "$BACKUP_DIR/manifest.txt"

echo "==> 3. 启动隔离临时 PostgreSQL 容器 ($CONTAINER_NAME)..."
docker run -d --name "$CONTAINER_NAME" \
  -e POSTGRES_USER="$DRILL_USER" \
  -e POSTGRES_PASSWORD="$DRILL_PASS" \
  -e POSTGRES_DB="$DRILL_DB" \
  -p "127.0.0.1:$DRILL_PORT:5432" \
  postgres:16 >/dev/null

echo "等待临时数据库完全就绪（经发布端口建立实际连接）..."
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

ready=0
for i in {1..40}; do
  if "$PYTHON_BIN" -c "import psycopg; psycopg.connect('host=127.0.0.1 port=$DRILL_PORT user=$DRILL_USER password=$DRILL_PASS dbname=$DRILL_DB connect_timeout=2')" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [[ $ready -eq 0 ]]; then
  echo "❌ 临时数据库启动超时" >&2
  exit 1
fi
echo "临时数据库已就绪。"

echo "==> 4. 执行 restore.sh 还原数据与附件..."
(
  cd "$INFRA_DIR"
  PG_RESTORE_IMAGE=postgres:16 bash restore.sh \
    --backup-dir "$BACKUP_DIR" \
    --database-url "postgresql://$DRILL_USER:$DRILL_PASS@127.0.0.1:$DRILL_PORT/$DRILL_DB" \
    --attachments-dir "$DRILL_DIR/attachments"
)

echo "==> 5. 运行 smoke_restore_verify.py 冒烟与端到端一致性校验..."
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" "$REPO_ROOT/scripts/smoke_restore_verify.py" \
  --database-url "postgresql+psycopg://$DRILL_USER:$DRILL_PASS@127.0.0.1:$DRILL_PORT/$DRILL_DB" \
  --attachments-dir "$DRILL_DIR/attachments"

echo "=========================================================="
echo "🎉 隔离恢复演练全部通过！"
echo "=========================================================="
