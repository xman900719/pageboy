#!/usr/bin/env bash
# 生产环境真题库安全补灌与可选重构脚本
# 严格遵循 docs/operations/production-environment.md 与 AGENTS.md 安全红线：
# 1. 默认走安全幂等增量模式，仅当显式传入 --rebuild 才执行清库重建；
# 2. 必须先完成生产前置热备份方可写入数据库；
# 3. 通过一次性只读挂载容器执行 scripts/ 与 .docx 转换缓存，解决容器无 LibreOffice 问题。
set -euo pipefail

PROD_ROOT="/media/xc/backup_ext4/pageboy-home/production"
CORPUS_DIR="/media/xc/backup_ntfs/中考题库/北京中考真题-富尔题库"

CONFIRM=0
REBUILD=0
CLEAN_DEMO=0

for arg in "$@"; do
  case "$arg" in
    --confirm) CONFIRM=1 ;;
    --rebuild) REBUILD=1 ;;
    --clean-demo) CLEAN_DEMO=1 ;;
    -h|--help)
      cat <<'EOF'
用法: bash infra/reseed_prod_corpus.sh --confirm [--clean-demo] [--rebuild]
  --confirm     显式确认执行生产库写入（必选，否则仅输出警告并退出）
  --clean-demo  灌库前运行 clean_demo_data.py 清理虚构演示题源（若同时传 --rebuild 则一并清理测试痕迹）
  --rebuild     危险：清删现有 official_exam 真题及关联曝光/作答记录后完全重建（仅限无须保留作答时使用）
EOF
      exit 0
      ;;
    *)
      echo "❌ 未知参数: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ "$CONFIRM" -ne 1 ]]; then
  echo "================================================================="
  echo "⚠️  【安全拦截】请显式确认生产库写入操作："
  echo "  • 目标生产根目录: $PROD_ROOT"
  echo "  • 富尔题库目录:   $CORPUS_DIR"
  echo "  • 默认行为:       前置热备份 + 幂等增量补灌（不删既有作答）"
  echo "  • 如需正式执行:   sudo -iu shutong-prod bash -c 'cd $PROD_ROOT/repo && bash infra/reseed_prod_corpus.sh --confirm'"
  echo "================================================================="
  exit 1
fi

if [[ "$(id -un)" != "shutong-prod" ]]; then
  echo "❌ 错误: 请使用 sudo -iu shutong-prod 身份运行本脚本（当前用户: $(id -un)）" >&2
  exit 1
fi

echo "================================================================="
echo "  [1/5] 检查生产目录、配置、富尔题库与预转换 .docx 缓存"
echo "================================================================="
if [[ ! -d "$PROD_ROOT" || ! -f "$PROD_ROOT/env/prod.env" ]]; then
  echo "❌ 错误: 生产环境根目录或 env/prod.env 不存在: $PROD_ROOT" >&2
  exit 1
fi
if [[ ! -d "$CORPUS_DIR" ]]; then
  echo "❌ 错误: 富尔题库目录不存在: $CORPUS_DIR" >&2
  exit 1
fi

CACHE_DIR="${SHUTONG_CONVERTED_CACHE_DIR:-$PROD_ROOT/data/converted_docx}"
if [[ ! -d "$CACHE_DIR" && -d "$PROD_ROOT/repo/.cache/converted_docx" ]]; then
  CACHE_DIR="$PROD_ROOT/repo/.cache/converted_docx"
fi
if [[ ! -d "$CACHE_DIR" ]]; then
  echo "❌ 错误: 未找到 .doc 预转换缓存目录（需先在宿主转换后同步至 $PROD_ROOT/data/converted_docx）" >&2
  exit 1
fi
echo "✓ 生产目录、富尔题库与预转换缓存就绪: $CACHE_DIR"

COMPOSE_CMD=(
  docker compose
  --env-file "$PROD_ROOT/env/prod.env"
  -f "$PROD_ROOT/repo/infra/compose.yaml"
  -f "$PROD_ROOT/repo/infra/compose.local.yaml"
)

# 在触库前，使用只读挂载容器校验 10 份 .doc 对应的缓存 .docx 均真实可用且非测试桩
"${COMPOSE_CMD[@]}" run --rm --no-deps \
  -v "$PROD_ROOT/repo/scripts:/app/scripts:ro" \
  -v "$CACHE_DIR:/app/.cache/converted_docx:ro" \
  api python -c '
from pathlib import Path
from shutong.corpus.exam_2025 import ALL_EXAM_PAPERS
cache_root = Path("/app/.cache/converted_docx")
missing = []
for p in ALL_EXAM_PAPERS:
    rel = p["pdf_relpath"]
    if rel.endswith(".doc"):
        target = cache_root / Path(rel).with_suffix(".docx")
        if not target.is_file():
            missing.append(f"缺失: {target}")
        else:
            raw = target.read_bytes()
            if b"SYNTHETIC TEST DATA" in raw or len(raw) <= 4096:
                missing.append(f"疑似测试桩或过小: {target} ({len(raw)} bytes)")
if missing:
    raise SystemExit("预转换缓存校验失败:\n" + "\n".join(missing))
print("✓ 全部 10 份 .doc 对应 .docx 预转换缓存校验通过")
'

echo "================================================================="
echo "  [2/5] 触发生产前置热备份 (强制门禁)"
echo "================================================================="
(
  cd "$PROD_ROOT/repo/infra"
  PATH="$PROD_ROOT/bin:$PATH" ENV_FILE="$PROD_ROOT/env/prod.env" bash backup.sh
)
echo "✓ 生产前置热备份完成"

echo "================================================================="
echo "  [3/5] 可选演示数据清理与测试痕迹清洗"
echo "================================================================="
if [[ "$CLEAN_DEMO" -eq 1 ]]; then
  CLEAN_ARGS=(--confirm)
  if [[ "$REBUILD" -eq 1 ]]; then
    CLEAN_ARGS+=(--clean-test-traces)
  fi
  "${COMPOSE_CMD[@]}" run --rm --no-deps \
    -v "$PROD_ROOT/repo/scripts:/app/scripts:ro" \
    api python /app/scripts/clean_demo_data.py "${CLEAN_ARGS[@]}"
  echo "✓ 演示数据清理完成"
else
  echo "• 未传入 --clean-demo，跳过清理步骤"
fi

echo "================================================================="
echo "  [4/5] 灌入北京中考 32 套真题与附件"
echo "================================================================="
SEED_ARGS=(--corpus-dir /corpus --converted-cache-dir /app/.cache/converted_docx)
if [[ "$REBUILD" -eq 1 ]]; then
  echo "⚠️ 已启用 --rebuild：将清理旧真题源后全量重建"
  SEED_ARGS+=(--rebuild)
fi

"${COMPOSE_CMD[@]}" run --rm --no-deps \
  -v "$PROD_ROOT/repo/scripts:/app/scripts:ro" \
  -v "$CORPUS_DIR:/corpus:ro" \
  -v "$CACHE_DIR:/app/.cache/converted_docx:ro" \
  api python /app/scripts/seed_real_corpus.py "${SEED_ARGS[@]}"
echo "✓ 生产环境真题库与物理附件写入完成"

echo "================================================================="
echo "  [5/5] 执行生产健康检查冒烟核验"
echo "================================================================="
curl -fsS http://127.0.0.1:18000/health/live | grep -q "alive" && echo "✓ /health/live PASS"
curl -fsS http://127.0.0.1:18000/health/ready | grep -q "ready" && echo "✓ /health/ready PASS"
echo "================================================================="
echo "  🎉 生产真题灌库流程安全完成！"
echo "================================================================="
