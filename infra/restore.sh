#!/usr/bin/env bash
# ST-024-C1/C2: only synthetic isolated restore. C3 real snapshot support is not yet authorized.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -eq 5 && "${1:-}" == --web-only && "$2" == --backup-dir && "$4" == --web-dist-dir ]]; then
  exec python3 "$root/scripts/web_artifact_provenance.py" restore "$3" "$5"
fi
if [[ $# -eq 5 && "${1:-}" == --exam-bank-only && "$2" == --backup-dir && "$4" == --exam-bank-dir ]]; then
  exec python3 "$root/scripts/exam_bank_backup.py" restore "$3" "$5"
fi
[[ $# -eq 3 && "${1:-}" == --local-drill ]] || { echo 'REFUSED: arbitrary database URL, --force and legacy restore disabled; use approved local drill' >&2; exit 1; }
root="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$root/scripts/st024c_local.py" restore "$2" "$3"
