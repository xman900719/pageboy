#!/usr/bin/env bash
# BACKUP TEMPLATE: joint DB + private attachments backup per docs/operations/backup-policy.md.
# First configure and test against staging; no RPO guarantee without monitoring.
#
# Env overrides (all optional except where noted):
#   ATTACHMENTS_DIR     private attachments root (default: /media/xc/backup_ext4/pageboy-home/production/data/attachments, resolved).
#                       Missing/inaccessible dir => fail closed.
#   MIGRATION_REVISION  optional assertion of the actual database revision; never an override.
# Local synthetic drill: backup.sh --local-drill <private-run-dir> source (no Docker/R2).
# Legacy BACKUP_OUTPUT_DIR mode is refused before Docker access.
#   ENV_FILE            env file to source and pass to docker compose (default: .env in infra/).
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
if [[ "${1:-}" == --local-drill ]]; then
  [[ $# -eq 3 ]] || { echo 'REFUSED: invalid local-drill arguments' >&2; exit 1; }
  exec python3 "$repo_root/scripts/st024c_local.py" backup "$2" "$3"
fi
[[ $# -eq 0 && -z "${BACKUP_OUTPUT_DIR:-}" ]] || { echo 'REFUSED: legacy local backup or invalid arguments' >&2; exit 1; }
ENV_FILE="${ENV_FILE:-.env}"
if [[ ! -f "$ENV_FILE" ]]; then echo "missing env file: $ENV_FILE" >&2; exit 1; fi
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a

[[ -z "${BACKUP_OUTPUT_DIR:-}" ]] || { echo 'REFUSED: legacy local backup mode' >&2; exit 1; }
# Serialize backup, deploy and rollback; no production lock acquired by the C5 installer.
STATE_DIR="$here/.local"
mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/artifact.lock"
flock -x 9
helper="$repo_root/scripts/web_artifact_provenance.py"
bank_helper="$repo_root/scripts/exam_bank_backup.py"
: "${RESTIC_REPOSITORY:?restic repository must be set}"
: "${RESTIC_PASSWORD_FILE:?restic password file required}"
command -v restic >/dev/null || { echo 'restic not installed' >&2; exit 1; }

# A missing attachment root is a failed joint backup, never a DB-only success.
attachments_requested="${ATTACHMENTS_DIR:-${SHUTONG_ATTACHMENTS_DIR:-/media/xc/backup_ext4/pageboy-home/production/data/attachments}}"
attachments_dir="$(cd "$attachments_requested" 2>/dev/null && pwd)" || {
  echo 'REFUSED: attachment directory missing or inaccessible' >&2; exit 1;
}
if [[ -n "${SHUTONG_ATTACHMENTS_DIR:-}" ]]; then
  mounted_dir="$(cd "$SHUTONG_ATTACHMENTS_DIR" 2>/dev/null && pwd)" || exit 1
  [[ "$mounted_dir" == "$attachments_dir" ]] || { echo 'REFUSED: attachment roots disagree' >&2; exit 1; }
fi
# The new corpus remains a sibling of the legacy attachment root.
bank_dir="${SHUTONG_EXAM_BANK_DIR:-$(dirname "$attachments_dir")/exam_bank_2018_2025}"
[[ "$bank_dir" == "$(dirname "$attachments_dir")/exam_bank_2018_2025" ]] || { echo 'REFUSED: corpus root must be an attachment sibling' >&2; exit 1; }
configured_bank_pin="${SHUTONG_EXAM_BANK_MANIFEST_SHA256:-}"
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
api_identity() {
  local tag cid image config_image tagged label deployed mounts
  tag="$(compose_db exec -T api printenv SHUTONG_APP_REVISION)" || return 1
  cid="$(compose_db ps -q api)" || return 1
  [[ "$cid" =~ ^[0-9a-f]{12,64}$ ]] || { echo 'REFUSED: ambiguous API container' >&2; return 1; }
  mounts="$(docker inspect --format '{{json .Mounts}}' "$cid")" || return 1
  python3 "$helper" mount "$mounts" "$attachments_dir" || return 1
  # Read only the relevant env keys from the running API; no secret dump.
  local live_pin live_bank_dir bank_mode
  live_pin="$(compose_db exec -T api python -c 'import os; print(os.getenv("SHUTONG_EXAM_BANK_MANIFEST_SHA256", ""))')" || return 1
  live_bank_dir="$(compose_db exec -T api python -c 'import os; print(os.getenv("SHUTONG_EXAM_BANK_DIR", ""))')" || return 1
  bank_mode=inactive
  if [[ -n "$live_pin" ]]; then
    [[ "$live_pin" =~ ^[0-9a-f]{64}$ && "$live_pin" == "$configured_bank_pin" && "$live_bank_dir" == /var/lib/shutong/exam_bank_2018_2025 ]] || return 1
    bank_mode=active
    python3 "$bank_helper" mount "$mounts" "$bank_dir" active || return 1
  elif [[ -n "$configured_bank_pin" ]]; then
    # Pre-release snapshot: old API has no mount or pin; capture staged corpus as well as legacy bytes.
    [[ "$configured_bank_pin" =~ ^[0-9a-f]{64}$ && -z "$live_bank_dir" ]] || return 1
    bank_mode=staged
    python3 "$bank_helper" mount "$mounts" "$bank_dir" staged || return 1
  else
    [[ -z "$live_bank_dir" ]] || { echo 'REFUSED: corpus configured in API without pin' >&2; return 1; }
    python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert not any(str(m.get("Destination", "")).startswith("/var/lib/shutong/exam_bank_2018_2025") for m in d)' "$mounts" || return 1
  fi
  printf 'exam_bank_mode=%s\nexam_bank_pin=%s\n' "$bank_mode" "$configured_bank_pin"
  # The old 0022 runtime predates relative-path storage; the new runtime must use the covered root.
  if [[ "$migration_revision" != 0022 ]]; then
    [[ "$(compose_db exec -T api printenv SHUTONG_SCHOOL_EXAMS_DIR)" == /var/lib/shutong/attachments/school-exams ]] || {
      echo 'REFUSED: school archive outside backed-up attachment root' >&2; return 1;
    }
  fi
  image="$(docker inspect --format '{{.Image}}' "$cid")" || return 1
  config_image="$(docker inspect --format '{{.Config.Image}}' "$cid")" || return 1
  [[ "$(docker inspect --format '{{.State.Running}}' "$cid")" == true ]] || return 1
  tagged="$(docker image inspect --format '{{.Id}}' "shutong-api:$tag")" || return 1
  label="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")" || return 1
  deployed="$(cat "$STATE_DIR/deployed-tag")" || return 1
  local meta
  meta="$(python3 "$helper" api "$tag" "$deployed" "$config_image" "$image" "$tagged" "$label")" || return 1
  if [[ "$label" =~ ^[0-9a-f]{40}$ ]]; then
    [[ "$(git -C "$repo_root" cat-file -t "$label")" == commit ]] || { echo 'REFUSED: API Git commit unavailable' >&2; return 1; }
  fi
  printf '%s\n' "$meta"
  printf 'app_revision=%s\ncontainer_id=%s\n' "$tag" "$cid"
}
api_before="$(api_identity)"
app_revision="$(sed -n 's/^app_revision=//p' <<<"$api_before")"
[[ "$app_revision" =~ ^[[:alnum:]_.-]+$ && "$app_revision" != unknown && "$app_revision" != dev ]] || { echo 'REFUSED: unknown application revision' >&2; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf "$work"; rm -f "$work.restic.json"' EXIT
read_refs() {
  local query
  query=$(cat <<'REFSQL'
SELECT COALESCE(json_agg(json_build_array(storage_key,sha256,byte_size,rel) ORDER BY storage_key,sha256,byte_size,rel), '[]'::json) FROM (SELECT storage_key,sha256,byte_size,to_jsonb(t)->>'relative_path' AS rel FROM public.source_attachments t UNION ALL SELECT storage_key,sha256,byte_size,to_jsonb(t)->>'relative_path' AS rel FROM public.school_paper_attachments t UNION ALL SELECT storage_key,sha256,byte_size,to_jsonb(t)->>'relative_path' AS rel FROM public.school_exam_papers t UNION ALL SELECT storage_key,sha256,byte_size,to_jsonb(t)->>'relative_path' AS rel FROM public.school_exam_reports t UNION ALL SELECT storage_key,sha256,byte_size,to_jsonb(t)->>'relative_path' AS rel FROM public.school_exam_report_attachments t) refs
REFSQL
)
  compose_db exec -T db sh -c 'exec psql -X -w -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"' _ "$query"
}
refs_before="$(read_refs)"
bank_pin="$(sed -n 's/^exam_bank_pin=//p' <<<"$api_before")"
read_bank_refs() {
  local query
  query=$(cat <<'BANKSQL'
SELECT COALESCE(json_agg(json_build_array(a.id,s.id,a.storage_key,a.sha256,a.byte_size,s.exam_year,s.subject,a.status,s.verified,s.title) ORDER BY a.id), '[]'::json) FROM public.source_documents s LEFT JOIN public.source_attachments a ON a.source_document_id=s.id WHERE s.source_class='official_exam' AND s.exam_year BETWEEN 2018 AND 2025
BANKSQL
)
  compose_db exec -T db sh -c 'exec psql -X -w -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"' _ "$query"
}
if [[ -n "$bank_pin" ]]; then bank_refs_before="$(read_bank_refs)"; fi
# A consistent pg_dump snapshot (custom format) from the compose db service.
docker compose --env-file "$ENV_FILE" -f compose.yaml exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$work/postgres.dump"
test -s "$work/postgres.dump"
[[ "$(read_revision)" == "$migration_revision" ]] || { echo 'REFUSED: database revision changed during dump' >&2; exit 1; }

# A changing/unreadable attachment tree makes tar fail under set -e.
tar czf "$work/attachments.tar.gz" -C "$attachments_dir" .
if [[ -n "$bank_pin" ]]; then
  printf '%s\n' "$bank_refs_before" | python3 "$bank_helper" capture "$bank_dir" "$work/exam-bank.tar.gz" "$bank_pin"
fi
[[ "$(read_revision)" == "$migration_revision" ]] || { echo 'REFUSED: database revision changed during joint backup' >&2; exit 1; }
web_meta="$(python3 "$helper" archive "$repo_root/apps/web/dist" "$STATE_DIR/web-provenance.json" "$work/web-dist.tar.gz")"
web_sha="$(sed -n 's/^web_source_git_sha=//p' <<<"$web_meta")"
if [[ "$web_sha" != UNVERIFIED ]]; then
  [[ "$(git -C "$repo_root" cat-file -t "$web_sha")" == commit ]] || { echo 'REFUSED: Web Git commit unavailable' >&2; exit 1; }
fi
[[ "$(api_identity)" == "$api_before" ]] || { echo 'REFUSED: API changed during backup' >&2; exit 1; }
[[ "$(read_revision)" == "$migration_revision" ]] || { echo 'REFUSED: DB changed during Web backup' >&2; exit 1; }

printf 'timestamp_utc=%s\napp_revision=%s\nmigration_revision=%s\nattachments_included=%s\nattachment_count=%s\n' \
  "$(date -u +%FT%TZ)" "$app_revision" "$migration_revision" "$attachments_included" "$attachment_count" > "$work/manifest.txt"

{
  if [[ -n "$bank_pin" ]]; then
    printf 'artifact_format=3\nexam_bank_manifest_sha256=%s\n' "$bank_pin"
  else
    printf 'artifact_format=2\n'
  fi
  grep -E '^api_(git_sha|image_id)=' <<<"$api_before"
  printf '%s\n' "$web_meta"
} >> "$work/manifest.txt"
checksum_files=(postgres.dump attachments.tar.gz web-dist.tar.gz manifest.txt)
if [[ -n "$bank_pin" ]]; then checksum_files+=(exam-bank.tar.gz); fi
( cd "$work" && sha256sum "${checksum_files[@]}" > SHA256SUMS )
python3 "$helper" verify "$work"
[[ "$(read_refs)" == "$refs_before" ]] || { echo 'REFUSED: attachment references changed during backup' >&2; exit 1; }
# Deliberately retain and verify all legacy copies until a separately authorized cleanup.
printf '%s\n' "$refs_before" | python3 "$helper" refs "$work/attachments.tar.gz"
if [[ -n "$bank_pin" ]]; then
  [[ "$(read_bank_refs)" == "$bank_refs_before" ]] || { echo 'REFUSED: corpus database references changed' >&2; exit 1; }
  printf '%s\n' "$bank_refs_before" | python3 "$bank_helper" verify "$work/exam-bank.tar.gz" "$bank_pin"
  [[ "$(api_identity)" == "$api_before" ]] || { echo 'REFUSED: corpus API changed during backup' >&2; exit 1; }
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
