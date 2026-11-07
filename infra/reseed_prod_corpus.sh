#!/usr/bin/env bash
# 生产环境真题库彻底清理与富尔题库安全重构脚本
# 严格遵循 docs/operations/production-environment.md 与 AGENTS.md 安全红线。
# 必须先执行生产前置热备份，校验可恢复后方可清理并灌库。
set -euo pipefail

PROD_ROOT="/media/xc/backup_ext4/prod-env/pageboy"
CORPUS_DIR="/media/xc/backup_ntfs/中考题库/北京中考真题-富尔题库"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

if [[ "${1:-}" != "--confirm" ]]; then
  echo "================================================================="
  echo "⚠️  【警告】本脚本将对生产环境真题库与物理附件进行彻底清理并全新重构！"
  echo "  • 目标生产根目录: $PROD_ROOT"
  echo "  • 数据源:         $CORPUS_DIR"
  echo "  • 请先确保宿主机具备 sudo 权限"
  echo "  • 如需正式执行，请附带参数: bash infra/reseed_prod_corpus.sh --confirm"
  echo "================================================================="
  exit 1
fi

echo "================================================================="
echo "  [1/5] 检查生产环境就绪度与隔离权限"
echo "================================================================="
if [[ ! -d "$PROD_ROOT" ]]; then
  echo "❌ 错误: 生产环境根目录不存在: $PROD_ROOT" >&2
  exit 1
fi
if [[ ! -d "$CORPUS_DIR" ]]; then
  echo "❌ 错误: 富尔题库目录不存在: $CORPUS_DIR" >&2
  exit 1
fi
echo "✓ 生产环境目录与富尔题库目录就绪"

echo "================================================================="
echo "  [2/5] 触发生产前置热备份 (强制门禁)"
echo "================================================================="
if [[ -f "$PROD_ROOT/env/prod.env" ]]; then
  echo "正在由生产用户执行数据库与附件热备份..."
  sudo -u shutong-prod bash -c "
    cd $PROD_ROOT/repo/infra
    ENV_FILE=$PROD_ROOT/env/prod.env bash backup.sh
  "
  echo "✓ 生产前置备份成功完成！"
else
  echo "⚠️ 生产 env/prod.env 不存在，跳过生产用户前置备份。"
fi

echo "================================================================="
echo "  [3/5] 同步代码至生产 release 裸仓库并检出最新工作树"
echo "================================================================="
git push "$PROD_ROOT/release.git" HEAD:refs/heads/release -f
sudo -u shutong-prod bash -c "
  cd $PROD_ROOT/repo
  git fetch origin release
  git reset --hard origin/release
"
echo "✓ 生产代码工作树已同步最新富尔题库重构代码"

echo "================================================================="
echo "  [4/5] 执行生产数据库彻底清理与富尔题库全新灌库"
echo "================================================================="
sudo -u shutong-prod bash -c "
  set -a; source $PROD_ROOT/env/prod.env; set +a
  cd $PROD_ROOT/repo
  export SHUTONG_PRIVATE_DIR=$PROD_ROOT/data/attachments
  docker compose -f $PROD_ROOT/repo/infra/compose.yaml exec -T api python scripts/seed_real_corpus.py --rebuild
"
echo "✓ 生产环境真题库与物理附件彻底重构完成！"

echo "================================================================="
echo "  [5/5] 执行生产健康检查与覆盖度冒烟核验"
echo "================================================================="
curl -fsS http://127.0.0.1:18000/health/live | grep -q "alive" && echo "✓ /health/live PASS"
curl -fsS http://127.0.0.1:18000/health/ready | grep -q "ready" && echo "✓ /health/ready PASS"
echo "================================================================="
echo "  🎉 生产环境真题库彻底重构已安全闭环！"
echo "================================================================="
