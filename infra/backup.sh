#!/usr/bin/env bash
# BACKUP TEMPLATE: first configure and test against staging; no RPO guarantee without monitoring.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
if [[ ! -f .env ]]; then echo 'missing infra/.env' >&2; exit 1; fi
# shellcheck source=/dev/null
set -a; source .env; set +a
: "${RESTIC_REPOSITORY:?restic repository must be set}"
: "${RESTIC_PASSWORD_FILE:?restic password file required}"
command -v restic >/dev/null || { echo 'restic not installed' >&2; exit 1; }
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
# A consistent pg_dump snapshot; immutable file assets must be backed up together when implemented.
docker compose --env-file .env -f compose.yaml exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$work/postgres.dump"
test -s "$work/postgres.dump"
sha256sum "$work/postgres.dump" > "$work/SHA256SUMS"
printf 'timestamp_utc=%s\napp_revision=%s\n' "$(date -u +%FT%TZ)" "${APP_REVISION:-unknown}" > "$work/manifest.txt"
# IMPORTANT: currently files/assets upload not implemented; add immutable asset directory to snapshot before real use.
restic backup "$work" --tag shutong-foundation
restic check
printf 'Backup finished. RESTORE TEST STILL REQUIRED.\n'
