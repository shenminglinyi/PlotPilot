#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REMOTE_HOST="${PLOTPILOT_OBSIDIAN_REMOTE_HOST:-45.197.149.138}"
REMOTE_USER="${PLOTPILOT_OBSIDIAN_REMOTE_USER:-root}"
REMOTE_PORT="${PLOTPILOT_OBSIDIAN_REMOTE_PORT:-7806}"
REMOTE_VAULT="${PLOTPILOT_OBSIDIAN_REMOTE_VAULT:-/www/wwwroot/plotpilot-novelpro/data/obsidian-vault}"
SSH_KEY="${PLOTPILOT_OBSIDIAN_SSH_KEY:-$HOME/.ssh/qidian_deploy_ed25519}"

LOCAL_VAULT="${PLOTPILOT_OBSIDIAN_LOCAL_VAULT:-$HOME/PlotPilot-Obsidian-Vault}"
LOG_DIR="${PLOTPILOT_OBSIDIAN_SYNC_LOG_DIR:-$PROJECT_ROOT/logs}"
BACKUP_ROOT="${PLOTPILOT_OBSIDIAN_SYNC_BACKUP_DIR:-$PROJECT_ROOT/data/obsidian-vault-backups}"
LOCK_DIR="${PLOTPILOT_OBSIDIAN_SYNC_LOCK:-$PROJECT_ROOT/.obsidian-sync.lock}"
DELETE_FLAG="${PLOTPILOT_OBSIDIAN_SYNC_DELETE:-1}"

mkdir -p "$LOCAL_VAULT" "$LOG_DIR" "$BACKUP_ROOT"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync skipped: another sync is running"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

timestamp="$(date '+%Y%m%d-%H%M%S')"
backup_dir="$BACKUP_ROOT/$timestamp"

rsync_args=(
  -az
  --backup
  --backup-dir "$backup_dir"
  -e "ssh -i $SSH_KEY -p $REMOTE_PORT -o StrictHostKeyChecking=no"
)

if [[ "$DELETE_FLAG" == "1" || "$DELETE_FLAG" == "true" ]]; then
  rsync_args+=(--delete)
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync start"
rsync "${rsync_args[@]}" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_VAULT/" "$LOCAL_VAULT/"

if [[ -d "$backup_dir" ]] && ! find "$backup_dir" -type f -print -quit | grep -q .; then
  rmdir "$backup_dir" 2>/dev/null || true
fi

file_count="$(find "$LOCAL_VAULT" -type f | wc -l | tr -d ' ')"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync done: $file_count files in $LOCAL_VAULT"
