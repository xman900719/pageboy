#!/usr/bin/env bash
# BACKUP TEMPLATE: joint DB + private attachments backup per docs/operations/backup-policy.md.
# First configure and test against staging; no RPO guarantee without monitoring.
#
# Env overrides (all optional except where noted):
#   ATTACHMENTS_DIR     private attachments root (default: /media/xc/backup_ext4/pageboy-home/production/data/attachments, resolved).
#                       Missing dir => loud warning; attachments NOT included in the artifact set.
#   MIGRATION_REVISION  override alembic head auto-detection (default: auto-detect, 'unknown' on failure).
#   BACKUP_OUTPUT_DIR   LOCAL DRILL MODE: when set, skip restic entirely and copy the artifact set
#                       (postgres.dump, attachments.tar.gz, SHA256SUMS, manifest.txt) into this directory.
#                       本地演练模式，非异地备份，不满足 3-2-1，不构成 AC-OPS-01。
#   ENV_FILE            env file to source and pass to docker compose (default: .env in infra/).
#                       The drill sets this to a generated /tmp env so no infra/.env is ever created.
#   COMPOSE_PROJECT_NAME  honored from ENV_FILE (exported via `set -a; source`) so `compose exec db`
#                       targets the drill project instead of the default one.
#   KUMA_PUSH_URL       optional Uptime Kuma push URL: on SUCCESSFUL backup+check+forget, send one
#                       push so Kuma's timeout (>12min silence) raises the "距上次成功备份>5h" alarm.
#                       Push failure is a WARNING only — the backup itself stays valid.
#   HEALTHCHECKS_PING_URL optional healthchecks.io ping URL: dead-man's-switch semantics (the
#                       exact match for AC-OPS-02's ">5h no successful backup → alert"): ping on
#                       success; silence beyond the check's period+grace (4h+1h=5h) triggers email.
#                       Push failure is a WARNING only — the backup itself stays valid.
#   RETENTION_ARGS      optional override of the restic forget args (default implements the policy
#                       numbers in docs/operations/backup-policy.md: 12×4h=48h 内 + 14 日 + 8 周 + 6 月).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
repo_root="$(cd .. && pwd)"
ENV_FILE="${ENV_FILE:-.env}"
if [[ ! -f "$ENV_FILE" ]]; then echo "missing env file: $ENV_FILE" >&2; exit 1; fi
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a

local_drill=0
if [[ -n "${BACKUP_OUTPUT_DIR:-}" ]]; then local_drill=1; fi

if [[ "$local_drill" -eq 0 ]]; then
  : "${RESTIC_REPOSITORY:?restic repository must be set}"
  : "${RESTIC_PASSWORD_FILE:?restic password file required}"
  command -v restic >/dev/null || { echo 'restic not installed' >&2; exit 1; }
fi

# Attachments dir: resolve; missing dir is allowed ONLY with a loud warning (attachments excluded).
attachments_requested="${ATTACHMENTS_DIR:-/media/xc/backup_ext4/pageboy-home/production/data/attachments}"
attachments_dir=""
if attachments_dir="$(cd "$attachments_requested" 2>/dev/null && pwd)"; then
  :
else
  attachments_dir=""
fi
attachments_included=no
attachment_count=0
if [[ -n "$attachments_dir" ]]; then
  attachments_included=yes
  attachment_count="$(find "$attachments_dir" -type f | wc -l | tr -d ' ')"
else
  echo "WARNING: attachments dir not found ($attachments_requested): 附件未包含在本次备份中！" >&2
fi

# Migration revision: alembic head of this checkout; guard failure -> 'unknown'.
migration_revision="${MIGRATION_REVISION:-unknown}"
if [[ "${MIGRATION_REVISION:-}" == "" && -x "$repo_root/.venv/bin/python" && -f "$repo_root/services/api/alembic.ini" ]]; then
  if detected="$(cd "$repo_root/services/api" && "$repo_root/.venv/bin/python" -m alembic heads 2>/dev/null | awk 'NR==1{print $1; exit}')"; then
    if [[ -n "$detected" ]]; then migration_revision="$detected"; fi
  fi
fi

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
# A consistent pg_dump snapshot (custom format) from the compose db service.
docker compose --env-file "$ENV_FILE" -f compose.yaml exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$work/postgres.dump"
test -s "$work/postgres.dump"

if [[ "$attachments_included" = yes ]]; then
  # tar of the attachments directory CONTENTS; restore extracts into an empty target dir.
  tar czf "$work/attachments.tar.gz" -C "$attachments_dir" .
  ( cd "$work" && sha256sum postgres.dump attachments.tar.gz > SHA256SUMS )
else
  ( cd "$work" && sha256sum postgres.dump > SHA256SUMS )
fi

printf 'timestamp_utc=%s\napp_revision=%s\nmigration_revision=%s\nattachments_included=%s\nattachment_count=%s\n' \
  "$(date -u +%FT%TZ)" "${APP_REVISION:-unknown}" "$migration_revision" "$attachments_included" "$attachment_count" > "$work/manifest.txt"

if [[ "$local_drill" -eq 1 ]]; then
  mkdir -p "$BACKUP_OUTPUT_DIR"
  cp "$work/postgres.dump" "$work/SHA256SUMS" "$work/manifest.txt" "$BACKUP_OUTPUT_DIR/"
  if [[ "$attachments_included" = yes ]]; then cp "$work/attachments.tar.gz" "$BACKUP_OUTPUT_DIR/"; fi
  echo 'WARNING: 本地演练模式，非异地备份，不满足 3-2-1（docs/operations/backup-policy.md）；不能据此宣称 AC-OPS-01 或任何 RPO/RTO。' >&2
  printf 'Local drill backup written to %s. THIS IS NOT AN OFFSITE BACKUP.\n' "$BACKUP_OUTPUT_DIR"
  exit 0
fi

# Production path (restic); artifact set now carries attachments alongside the DB snapshot.
restic backup "$work" --tag shutong-foundation
restic check
# Retention per docs/operations/backup-policy.md: 12×4 小时快照=48h 内 + 每日 14 + 每周 8 + 每月 6。
restic forget --keep-within 48h --keep-daily 14 --keep-weekly 8 --keep-monthly 6 ${RETENTION_ARGS:-} --prune
restic check
# AC-OPS-02 告警挂钩：成功才 push，Kuma 侧按静默超时告警；推送失败不判备份失败。
if [[ -n "${KUMA_PUSH_URL:-}" ]]; then
  curl -fsS --max-time 10 "${KUMA_PUSH_URL}" >/dev/null \
    || echo 'WARNING: Kuma push failed (备份本身有效，但告警通道可能感知不到本次成功)' >&2
fi
# healthchecks.io dead-man's switch（AC-OPS-02 首选通道）：成功 ping；>period+grace 静默即邮件告警。
if [[ -n "${HEALTHCHECKS_PING_URL:-}" ]]; then
  curl -fsS --max-time 10 "${HEALTHCHECKS_PING_URL}" >/dev/null \
    || echo 'WARNING: healthchecks.io ping failed (备份本身有效，但 dead-man switch 可能感知不到本次成功)' >&2
fi
printf 'Backup finished. RESTORE TEST STILL REQUIRED.\n'
