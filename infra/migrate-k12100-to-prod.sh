#!/usr/bin/env bash
# 将宿主机 k12100 凭据、DeepSeek AI 密钥与浏览器登录会话安全迁移至生产隔离目录（需 root）。
# 特性：幂等、零明文回显、严格收紧权限（目录 0700、文件 0600，属主 shutong-prod），绝不覆盖既有生产令牌或数据库配置。
#
# 用法：
#   sudo bash infra/migrate-k12100-to-prod.sh                   # 仅迁移至生产环境
#   sudo bash infra/migrate-k12100-to-prod.sh --cleanup-legacy  # 迁移校验通过后同时清除 /home/xc/.config/shutong
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "错误：写入生产隔离目录需要 root 权限（请使用 sudo bash $0）" >&2; exit 1; }

DEV_USER="${SUDO_USER:-xc}"
PROD_USER="shutong-prod"
HOME_ROOT="${PAGEBOY_HOME:-/media/xc/backup_ext4/pageboy-home}"
DEV_HOME="$HOME_ROOT/development"
PROD_HOME="$HOME_ROOT/production"
PROD_ENV_FILE="$PROD_HOME/env/prod.env"
PROD_K12_DIR="$PROD_HOME/k12100"
PROD_API_URL="${K12100_PROD_API_URL:-http://127.0.0.1:8180}"

cleanup_legacy=0
source_dir=""
for arg in "$@"; do
  case "$arg" in
    --cleanup-legacy) cleanup_legacy=1 ;;
    --source-dir=*) source_dir="${arg#*=}" ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

id "$PROD_USER" >/dev/null 2>&1 || { echo "错误：生产用户 $PROD_USER 不存在" >&2; exit 1; }
[[ -d "$PROD_HOME" ]] || { echo "错误：生产目录 $PROD_HOME 不存在" >&2; exit 1; }
[[ -f "$PROD_ENV_FILE" ]] || { echo "错误：生产环境配置文件不存在: $PROD_ENV_FILE" >&2; exit 1; }

DEV_HOME_DIR="$(getent passwd "$DEV_USER" | cut -d: -f6)"
LEGACY_DIR="${DEV_HOME_DIR:-/home/$DEV_USER}/.config/shutong"
if [[ -z "$source_dir" ]]; then
  if [[ -d "$LEGACY_DIR" && -f "$LEGACY_DIR/k12100.env" ]]; then
    source_dir="$LEGACY_DIR"
  elif [[ -d "$DEV_HOME/k12100" && -f "$DEV_HOME/k12100/k12100.env" ]]; then
    source_dir="$DEV_HOME/k12100"
  else
    echo "错误：未找到源 k12100 配置目录（既不存在 $LEGACY_DIR 也不存在 $DEV_HOME/k12100）" >&2
    exit 1
  fi
fi

SRC_ENV_FILE="$source_dir/k12100.env"
[[ -f "$SRC_ENV_FILE" ]] || { echo "错误：源凭据文件不存在: $SRC_ENV_FILE" >&2; exit 1; }
[[ ! -L "$SRC_ENV_FILE" ]] || { echo "错误：拒绝读取符号链接: $SRC_ENV_FILE" >&2; exit 1; }

install -d -o "$PROD_USER" -g "$PROD_USER" -m 700 "$PROD_K12_DIR" "$PROD_K12_DIR/probe_snapshot"

# 使用内联 Python 原子合并 prod.env 与 production/k12100/k12100.env（全程绝不打印明文）
python3 - "$SRC_ENV_FILE" "$PROD_ENV_FILE" "$PROD_K12_DIR/k12100.env" "$PROD_API_URL" <<'PY'
from __future__ import annotations

import os
from pathlib import Path
import sys

src_env_path = Path(sys.argv[1])
prod_env_path = Path(sys.argv[2])
prod_k12_env_path = Path(sys.argv[3])
prod_api_url = sys.argv[4].strip().rstrip("/")


def parse_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    mapping: dict[str, str] = {}
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        mapping[k.strip()] = v.strip().strip('"').strip("'")
    return lines, mapping


def write_atomic_0600(path: Path, content: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def mask(val: str) -> str:
    if not val:
        return "未配置"
    if len(val) <= 8:
        return "***"
    return f"{val[:4]}***{val[-4:]}"


_, src_map = parse_env(src_env_path)
prod_lines, prod_map = parse_env(prod_env_path)
_, existing_k12_map = parse_env(prod_k12_env_path) if prod_k12_env_path.exists() else ([], {})

# 1. 安全补充 AI/Vision 密钥到 prod.env（绝不覆盖既有 POSTGRES_*/SHUTONG_*_TOKEN/TUNNEL 等字段）
ai_keys = (
    "DEEPSEEK_API_KEY",
    "SHUTONG_AI_API_KEY",
    "SHUTONG_VISION_API_KEY",
    "DEEPSEEK_BASE_URL",
    "SHUTONG_AI_BASE_URL",
    "SHUTONG_VISION_BASE_URL",
    "SHUTONG_AI_MODEL",
    "SHUTONG_TEXT_ENRICH_MODEL",
    "SHUTONG_VISION_MODEL",
)
ai_updates: dict[str, str] = {}
resolved_ai_key = (
    src_map.get("DEEPSEEK_API_KEY")
    or src_map.get("SHUTONG_AI_API_KEY")
    or src_map.get("SHUTONG_VISION_API_KEY")
    or ""
).strip()
if resolved_ai_key:
    ai_updates["DEEPSEEK_API_KEY"] = resolved_ai_key
    ai_updates["SHUTONG_AI_API_KEY"] = (src_map.get("SHUTONG_AI_API_KEY") or resolved_ai_key).strip()
    ai_updates["SHUTONG_VISION_API_KEY"] = (src_map.get("SHUTONG_VISION_API_KEY") or resolved_ai_key).strip()
for k in ai_keys:
    if k not in ai_updates and src_map.get(k, "").strip():
        ai_updates[k] = src_map[k].strip()

updated_prod_lines: list[str] = []
seen_in_prod: set[str] = set()
for raw in prod_lines:
    s = raw.strip()
    if s and not s.startswith("#") and "=" in s:
        k = s.split("=", 1)[0].strip()
        if k in ai_updates:
            updated_prod_lines.append(f"{k}={ai_updates[k]}")
            seen_in_prod.add(k)
            continue
    updated_prod_lines.append(raw)
for k in ai_keys:
    if k in ai_updates and k not in seen_in_prod:
        updated_prod_lines.append(f"{k}={ai_updates[k]}")

write_atomic_0600(prod_env_path, "\n".join(updated_prod_lines).rstrip() + "\n")

# 2. 生成生产专属 k12100.env（SHUTONG_ADMIN_TOKEN 必须取 prod.env，绝不复用开发令牌）
prod_admin_token = (prod_map.get("SHUTONG_ADMIN_TOKEN") or prod_map.get("SHUTONG_TOKEN") or "").strip()
k12_map = dict(existing_k12_map)
for k in ("K12100_USERNAME", "K12100_PASSWORD"):
    if src_map.get(k, "").strip():
        k12_map[k] = src_map[k].strip()
k12_map["K12100_PAGEBOY_API_URL"] = prod_api_url
if prod_admin_token:
    k12_map["SHUTONG_ADMIN_TOKEN"] = prod_admin_token
k12_map.update(ai_updates)

ordered = [
    "K12100_USERNAME",
    "K12100_PASSWORD",
    "K12100_PAGEBOY_API_URL",
    "SHUTONG_ADMIN_TOKEN",
    *ai_keys,
]
out_lines = ["# 书童生产环境 k12100 与 AI 私密凭据（0600 shutong-prod 专属）"]
seen_k12: set[str] = set()
for k in ordered:
    if k in k12_map and k12_map[k]:
        out_lines.append(f"{k}={k12_map[k]}")
        seen_k12.add(k)
for k in sorted(k12_map):
    if k not in seen_k12 and k12_map[k]:
        out_lines.append(f"{k}={k12_map[k]}")
write_atomic_0600(prod_k12_env_path, "\n".join(out_lines) + "\n")

print(f"✓ 已安全更新生产 prod.env (AI Key: {mask(resolved_ai_key)})")
print(f"✓ 已安全写入生产 k12100.env (API URL: {prod_api_url}, Admin Token: {mask(prod_admin_token)})")
PY

chown "$PROD_USER:$PROD_USER" "$PROD_ENV_FILE" "$PROD_K12_DIR/k12100.env"
chmod 600 "$PROD_ENV_FILE" "$PROD_K12_DIR/k12100.env"

# 3. 迁移浏览器登录会话（仅复制浏览器 Profile，绝不把开发去重台账或采集快照带入生产）
if [[ -d "$source_dir/k12100-browser-profile" ]]; then
  install -d -o "$PROD_USER" -g "$PROD_USER" -m 700 "$PROD_K12_DIR/k12100-browser-profile"
  rsync -a --delete --chown="$PROD_USER:$PROD_USER" \
    "$source_dir/k12100-browser-profile/" "$PROD_K12_DIR/k12100-browser-profile/"
  chmod 700 "$PROD_K12_DIR/k12100-browser-profile"
  echo "✓ 已迁移 k12100-browser-profile 至 $PROD_K12_DIR/k12100-browser-profile"
fi

# 4. 初始化生产专属空去重台账（不覆盖已有的生产台账，不存在则初始化为空）
if [[ ! -f "$PROD_K12_DIR/k12100-synced.json" ]]; then
  printf '{\n  "synced": {}\n}\n' > "$PROD_K12_DIR/k12100-synced.json"
  chown "$PROD_USER:$PROD_USER" "$PROD_K12_DIR/k12100-synced.json"
  chmod 600 "$PROD_K12_DIR/k12100-synced.json"
  echo "✓ 已初始化生产空去重台账: $PROD_K12_DIR/k12100-synced.json"
fi

chown -R "$PROD_USER:$PROD_USER" "$PROD_K12_DIR"
chmod 700 "$PROD_K12_DIR" "$PROD_K12_DIR/probe_snapshot"
chmod 600 "$PROD_K12_DIR/k12100.env" "$PROD_K12_DIR/k12100-synced.json"

if [[ "$cleanup_legacy" -eq 1 && -d "$LEGACY_DIR" ]]; then
  if [[ ! -d "$DEV_HOME/k12100" || ! -f "$DEV_HOME/k12100/k12100.env" ]]; then
    echo "错误：尚未检测到开发环境 $DEV_HOME/k12100/k12100.env，拒绝删除 $LEGACY_DIR！" >&2
    exit 1
  fi
  rm -rf "$LEGACY_DIR"
  echo "✓ 已彻底清除旧全局目录: $LEGACY_DIR"
fi
