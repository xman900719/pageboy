#!/usr/bin/env bash
# BACKUP TEMPLATE: joint DB + private attachments backup per docs/operations/backup-policy.md.
# First configure and test against staging; no RPO guarantee without monitoring.
#
# Env overrides (all optional except where noted):
#   ATTACHMENTS_DIR     private attachments root (default: /media/xc/backup_ext4/pageboy-home/production/data/attachments, resolved).
#                       Missing/inaccessible dir => fail closed.
#   MIGRATION_REVISION  optional assertion of the actual database revision; never an override.
#   BACKUP_OUTPUT_DIR   LOCAL DRILL MODE: when set, skip restic entirely and copy the artifact set
#                       (postgres.dump, attachments.tar.gz, SHA256SUMS, manifest.txt) into this directory.
#                       本地演练模式，非异地备份，不满足 3-2-1，不构成 AC-OPS-01。
#   ENV_FILE            env file to source and pass to docker compose (default: .env in infra/).
#                       The drill sets this to a generated /tmp env so no infra/.env is ever created.
#   COMPOSE_PROJECT_NAME  honored from ENV_FILE (exported via `set -a; source`) so `compose exec db`
#                       targets the drill project instead of the default one.
#   KUMA_PUSH_URL       optional Uptime Kuma push URL: on SUCCESSFUL backup+check, send one
#                       push so Kuma's timeout (>12min silence) raises the "距上次成功备份>5h" alarm.
#                       Push failure is a WARNING only — the backup itself stays valid.
#   HEALTHCHECKS_PING_URL optional healthchecks.io ping URL: dead-man's-switch semantics (the
#                       exact match for AC-OPS-02's ">5h no successful backup → alert"): ping on
#                       success; silence beyond the check's period+grace (4h+1h=5h) triggers email.
#                       Push failure is a WARNING only — the backup itself stays valid.
# Retention is separate, explicitly authorized maintenance; backup never forgets/prunes.
set -euo pipefail
umask 077
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
repo_root="$(cd .. && pwd)"
ENV_FILE="${ENV_FILE:-.env}"
if [[ ! -f "$ENV_FILE" ]]; then echo "missing env file: $ENV_FILE" >&2; exit 1; fi
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a

local_drill=0
if [[ -n "${BACKUP_OUTPUT_DIR:-}" ]]; then
  local_drill=1
  [[ ! -e "$BACKUP_OUTPUT_DIR" || ( -d "$BACKUP_OUTPUT_DIR" && -z "$(ls -A "$BACKUP_OUTPUT_DIR")" ) ]] || {
    echo 'REFUSED: local drill output must be empty' >&2; exit 1;
  }
fi

if [[ "$local_drill" -eq 0 ]]; then
  : "${RESTIC_REPOSITORY:?restic repository must be set}"
  : "${RESTIC_PASSWORD_FILE:?restic password file required}"
  command -v restic >/dev/null || { echo 'restic not installed' >&2; exit 1; }
fi

# A missing attachment root is a failed joint backup, never a DB-only success.
attachments_requested="${ATTACHMENTS_DIR:-${SHUTONG_ATTACHMENTS_DIR:-/media/xc/backup_ext4/pageboy-home/production/data/attachments}}"
attachments_dir="$(cd "$attachments_requested" 2>/dev/null && pwd)" || {
  echo 'REFUSED: attachment directory missing or inaccessible' >&2; exit 1;
}
if [[ -n "${SHUTONG_ATTACHMENTS_DIR:-}" && "$local_drill" -eq 0 ]]; then
  mounted_dir="$(cd "$SHUTONG_ATTACHMENTS_DIR" 2>/dev/null && pwd)" || exit 1
  [[ "$mounted_dir" == "$attachments_dir" ]] || { echo 'REFUSED: attachment roots disagree' >&2; exit 1; }
fi
attachments_included=yes
attachment_count="$(find "$attachments_dir" -type f | wc -l | tr -d ' ')"
compose_db() { docker compose --env-file "$ENV_FILE" -f compose.yaml "$@"; }
read_revision() {
  compose_db exec -T db sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT version_num FROM alembic_version"'
}
migration_revision="$(read_revision)"
[[ "$migration_revision" =~ ^[[:alnum:]_]+$ && "$migration_revision" != unknown ]] || { echo 'REFUSED: unknown or multiple database revisions' >&2; exit 1; }
[[ -z "${MIGRATION_REVISION:-}" || "$MIGRATION_REVISION" == "$migration_revision" ]] || {
  echo 'REFUSED: expected database revision differs from actual revision' >&2; exit 1;
}
if [[ "$local_drill" -eq 0 ]]; then
  app_revision="$(compose_db exec -T api printenv SHUTONG_APP_REVISION)"
else
  app_revision="${APP_REVISION:-local-drill}"
fi
[[ "$app_revision" =~ ^[[:alnum:]_.-]+$ && "$app_revision" != unknown && "$app_revision" != dev ]] || { echo 'REFUSED: unknown application revision' >&2; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf "$work"; rm -f "$work.restic.json"' EXIT
# A consistent pg_dump snapshot (custom format) from the compose db service.
docker compose --env-file "$ENV_FILE" -f compose.yaml exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$work/postgres.dump"
test -s "$work/postgres.dump"
[[ "$(read_revision)" == "$migration_revision" ]] || { echo 'REFUSED: database revision changed during dump' >&2; exit 1; }

# A changing/unreadable attachment tree makes tar fail under set -e.
tar czf "$work/attachments.tar.gz" -C "$attachments_dir" .
[[ "$(read_revision)" == "$migration_revision" ]] || { echo 'REFUSED: database revision changed during joint backup' >&2; exit 1; }
( cd "$work" && sha256sum postgres.dump attachments.tar.gz > SHA256SUMS && sha256sum -c SHA256SUMS )

printf 'timestamp_utc=%s\napp_revision=%s\nmigration_revision=%s\nattachments_included=%s\nattachment_count=%s\n' \
  "$(date -u +%FT%TZ)" "$app_revision" "$migration_revision" "$attachments_included" "$attachment_count" > "$work/manifest.txt"

if [[ "$local_drill" -eq 1 ]]; then
  mkdir -p "$BACKUP_OUTPUT_DIR"
  cp "$work/postgres.dump" "$work/SHA256SUMS" "$work/manifest.txt" "$BACKUP_OUTPUT_DIR/"
  cp "$work/attachments.tar.gz" "$BACKUP_OUTPUT_DIR/"
  echo 'WARNING: 本地演练模式，非异地备份，不满足 3-2-1（docs/operations/backup-policy.md）；不能据此宣称 AC-OPS-01 或任何 RPO/RTO。' >&2
  printf 'Local drill backup written to %s. THIS IS NOT AN OFFSITE BACKUP.\n' "$BACKUP_OUTPUT_DIR"
  exit 0
fi

# Backup and verify the specific snapshot; destructive retention is separate maintenance.
restic backup "$work" --tag shutong-foundation --json > "$work.restic.json"
snapshot_id="$(python3 - "$work.restic.json" <<'PYJSON'
import json, re, sys
rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
ids = [row.get('snapshot_id', '') for row in rows if row.get('message_type') == 'summary']
if len(ids) != 1 or not re.fullmatch(r'[0-9a-f]{8,64}', ids[0]):
    sys.exit('REFUSED: restic did not return a unique snapshot ID')
print(ids[0])
PYJSON
)"
restic check
restic snapshots --json "$snapshot_id" | python3 -c 'import json,sys; s=json.load(sys.stdin); sys.exit(0 if len(s)==1 and s[0]["id"].startswith(sys.argv[1]) and "shutong-foundation" in s[0].get("tags", []) else "snapshot not confirmed")' "$snapshot_id"
printf 'BACKUP_SNAPSHOT_OK=%s\n' "$snapshot_id"
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
