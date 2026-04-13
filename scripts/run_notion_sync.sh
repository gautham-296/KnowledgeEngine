#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_DIR="$PROJECT_ROOT/.cron"
LOCK_DIR="$STATE_DIR/notion_sync.lock"
LAST_RUN_FILE="$STATE_DIR/notion_sync.last_success"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/notion_sync.log"
MIN_INTERVAL_SECONDS=259200

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$PROJECT_ROOT/engine/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/engine/bin/python"
else
    PYTHON_BIN="python3"
fi

mkdir -p "$STATE_DIR" "$LOG_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR"
}

trap cleanup EXIT

timestamp() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

now_epoch="$(date +%s)"

if [[ -f "$LAST_RUN_FILE" ]]; then
    last_success_epoch="$(cat "$LAST_RUN_FILE")"
    if [[ "$last_success_epoch" =~ ^[0-9]+$ ]]; then
        elapsed=$((now_epoch - last_success_epoch))
        if (( elapsed < MIN_INTERVAL_SECONDS )); then
            printf '[%s] Skipping Notion sync; last successful run was %ss ago.\n' "$(timestamp)" "$elapsed" >> "$LOG_FILE"
            exit 0
        fi
    fi
fi

printf '[%s] Starting Notion sync.\n' "$(timestamp)" >> "$LOG_FILE"

cd "$PROJECT_ROOT"

if "$PYTHON_BIN" notion_connection.py >> "$LOG_FILE" 2>&1; then
    printf '%s\n' "$now_epoch" > "$LAST_RUN_FILE"
    printf '[%s] Notion sync completed successfully.\n' "$(timestamp)" >> "$LOG_FILE"
else
    printf '[%s] Notion sync failed.\n' "$(timestamp)" >> "$LOG_FILE"
    exit 1
fi