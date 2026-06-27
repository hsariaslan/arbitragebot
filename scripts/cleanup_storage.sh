#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-7}"
DELETE_CSV="${DELETE_CSV:-0}"
DRY_RUN="${DRY_RUN:-1}"

echo "Project root: $ROOT"
echo "DRY_RUN=$DRY_RUN LOG_RETENTION_DAYS=$LOG_RETENTION_DAYS DELETE_CSV=$DELETE_CSV"
echo
echo "Before:"
du -sh "$ROOT/logs" "$ROOT/data" 2>/dev/null || true

echo
echo "Old log files:"
if [[ -d "$ROOT/logs" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    find "$ROOT/logs" -type f \
      \( -name 'arbitragebot.log.*' -o -name 'bot-logs-*.log' -o -name 'coirnabot*.log*' \) \
      -mtime +"$LOG_RETENTION_DAYS" -print
  else
    find "$ROOT/logs" -type f \
      \( -name 'arbitragebot.log.*' -o -name 'bot-logs-*.log' -o -name 'coirnabot*.log*' \) \
      -mtime +"$LOG_RETENTION_DAYS" -print -delete
  fi
fi

echo
if [[ "$DELETE_CSV" == "1" ]]; then
  echo "CSV snapshot files:"
  if [[ -d "$ROOT/data" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      find "$ROOT/data" -type f -name '*.csv' -print
    else
      find "$ROOT/data" -type f -name '*.csv' -print -delete
    fi
  fi
else
  echo "Skipping CSV snapshots. Set DELETE_CSV=1 to remove data/*/*.csv."
fi

echo
echo "After:"
du -sh "$ROOT/logs" "$ROOT/data" 2>/dev/null || true

if [[ "$DRY_RUN" == "1" ]]; then
  echo
  echo "Dry run only. Re-run with DRY_RUN=0 after stopping the bot service."
fi
