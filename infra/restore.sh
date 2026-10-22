#!/usr/bin/env bash
# RESTORE TEMPLATE: isolated restores ONLY — never point this at production.
# See docs/operations/recovery-runbook.md and infra/restore-not-automatic.md.
#
# Usage: restore.sh --backup-dir DIR --database-url URL --attachments-dir DIR
#
# Backup layout (produced by infra/backup.sh): postgres.dump, attachments.tar.gz,
# SHA256SUMS, manifest.txt.
#
# Dependencies (kept minimal): docker (pg_restore runs via the postgres:16-alpine image —
# the same tag infra/compose.yaml already uses, so any host that can run the compose db
# can restore; override with PG_RESTORE_IMAGE if that tag is unavailable locally, e.g. on
# an air-gapped host) and python3 (stdlib only, for DATABASE_URL parsing).
# The target database must be reachable over the host network (docker run --network host).
# Guards: refuses a database whose name does not start with "pageboy"; refuses a non-empty
# --attachments-dir so existing files are never overwritten.
set -euo pipefail

backup_dir='' database_url='' attachments_dir=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-dir) backup_dir="$2"; shift 2 ;;
    --database-url) database_url="$2"; shift 2 ;;
    --attachments-dir) attachments_dir="$2"; shift 2 ;;
    *) echo "unknown argument: $1 (usage: restore.sh --backup-dir DIR --database-url URL --attachments-dir DIR)" >&2; exit 2 ;;
  esac
done
: "${backup_dir:?--backup-dir required}"
: "${database_url:?--database-url required}"
: "${attachments_dir:?--attachments-dir required}"

for f in SHA256SUMS postgres.dump manifest.txt; do
  if [[ ! -f "$backup_dir/$f" ]]; then echo "missing $backup_dir/$f" >&2; exit 1; fi
done

echo "Verifying SHA256SUMS in $backup_dir ..."
( cd "$backup_dir" && sha256sum -c SHA256SUMS )

# Parse the DATABASE_URL (postgres:// or postgresql://) with the stdlib only.
parsed="$(python3 - "$database_url" <<'PY'
import sys
from urllib.parse import urlparse, unquote
url = urlparse(sys.argv[1])
print("\t".join([
    unquote(url.username or ""),
    unquote(url.password or ""),
    url.hostname or "127.0.0.1",
    str(url.port or 5432),
    (url.path or "").lstrip("/"),
]))
PY
)"
IFS=$'\t' read -r db_user db_pass db_host db_port db_name <<<"$parsed"

case "$db_name" in
  pageboy*) ;;
  *) echo "REFUSED: database name '$db_name' does not start with 'pageboy' (destructive-op guard; isolated restores only)" >&2; exit 1 ;;
esac

if [[ -f "$backup_dir/attachments.tar.gz" ]]; then
  if [[ -e "$attachments_dir" && -n "$(ls -A "$attachments_dir")" ]]; then
    echo "REFUSED: --attachments-dir exists and is not empty: $attachments_dir (refusing to overwrite)" >&2; exit 1
  fi
  mkdir -p "$attachments_dir"
  tar xzf "$backup_dir/attachments.tar.gz" -C "$attachments_dir"
  echo "Attachments restored into $attachments_dir"
else
  echo "WARNING: attachments.tar.gz missing from backup; attachments were NOT restored" >&2
fi

echo "Restoring postgres.dump into $db_host:$db_port/$db_name (isolated target) ..."
PG_RESTORE_IMAGE="${PG_RESTORE_IMAGE:-postgres:16-alpine}"
docker run --rm --network host -i -e PGPASSWORD="$db_pass" "$PG_RESTORE_IMAGE" \
  pg_restore -h "$db_host" -p "$db_port" -U "$db_user" -d "$db_name" --no-owner \
  < "$backup_dir/postgres.dump"
echo "pg_restore finished."

restored_revision="$(sed -n 's/^migration_revision=//p' "$backup_dir/manifest.txt")"
echo "Restored backup manifest:"
grep -E '^(timestamp_utc|app_revision|migration_revision|attachments_included|attachment_count)=' "$backup_dir/manifest.txt"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
current_head=unknown
if [[ -x "$repo_root/.venv/bin/python" && -f "$repo_root/services/api/alembic.ini" ]]; then
  if detected="$(cd "$repo_root/services/api" && "$repo_root/.venv/bin/python" -m alembic heads 2>/dev/null | awk 'NR==1{print $1; exit}')"; then
    if [[ -n "$detected" ]]; then current_head="$detected"; fi
  fi
fi
if [[ "$restored_revision" != "$current_head" ]]; then
  echo "WARNING: restored migration_revision ('$restored_revision') != current repo head ('$current_head'); check out the matching application revision before serving traffic." >&2
else
  echo "Restored migration_revision matches current repo head: $restored_revision"
fi
printf 'RESTORE COMPLETED (isolated). Human review against the runbook is still required.\n'
