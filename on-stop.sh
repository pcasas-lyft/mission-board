#!/bin/bash
# Stop hook — runs every time a Claude Code agent session ends.
# 1. Archives old done tasks
# 2. Regenerates WORKSTATUS.md + DONELOG.md
# 3. Fires a Mac notification with the task name (only when task is known)

DIR="$(dirname "$0")"

# 1. Archive done tasks older than 3 days
python3 "$DIR/archive-tasks.py" 2>/dev/null

# 2. Regenerate WORKSTATUS.md and DONELOG.md
python3 "$DIR/gen-status.py" 2>/dev/null
python3 "$DIR/gen-donelog.py" 2>/dev/null

# 3. Build notification scoped to this agent's branch/task
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# Derive the session task file path (matches what auto-claim-task.py writes)
# Replace / with - to make it a safe filename component
SAFE_BRANCH="${BRANCH//\//-}"
TASK_ID_FILE="${TMPDIR:-/tmp}/claude-task-${SAFE_BRANCH}.id"

# Pass both the branch and the task ID file — notif-summary.py tries task file first
NOTIF=$(python3 "$DIR/notif-summary.py" "$DIR/tasks.json" "$BRANCH" "$TASK_ID_FILE" 2>/dev/null)

# Only notify if we have something useful to say
if [[ -z "$NOTIF" ]]; then
  exit 0
fi

# Use terminal-notifier if available (click opens the tracker),
# fall back to osascript on macOS, silent on other platforms
if command -v terminal-notifier &>/dev/null; then
  terminal-notifier \
    -title "Agent Done 🤖" \
    -message "$NOTIF" \
    -open "http://localhost:3456" \
    -sound Glass 2>/dev/null || true
elif [[ "$OSTYPE" == "darwin"* ]]; then
  osascript -e "display notification \"$NOTIF\" with title \"Agent Done 🤖\" sound name \"Glass\"" 2>/dev/null || true
fi
