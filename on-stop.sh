#!/bin/bash
# Stop hook — runs every time a Claude Code agent session ends.
# 1. Archives old done tasks
# 2. Regenerates WORKSTATUS.md
# 3. Fires a Mac notification with the task name

DIR="$(dirname "$0")"

# 1. Archive done tasks older than 3 days
python3 "$DIR/archive-tasks.py" 2>/dev/null

# 2. Regenerate WORKSTATUS.md and DONELOG.md
python3 "$DIR/gen-status.py" 2>/dev/null
python3 "$DIR/gen-donelog.py" 2>/dev/null

# 3. Build notification scoped to this agent's branch/task
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
NOTIF=$(python3 "$DIR/notif-summary.py" "$DIR/tasks.json" "$BRANCH" 2>/dev/null)

# Use terminal-notifier if available (click opens the tracker),
# otherwise fall back to plain osascript
if command -v terminal-notifier &>/dev/null; then
  terminal-notifier \
    -title "Agent Done 🤖" \
    -message "$NOTIF" \
    -open "http://localhost:3456" \
    -sound Glass 2>/dev/null || true
else
  osascript -e "display notification \"$NOTIF\" with title \"Agent Done 🤖\" sound name \"Glass\"" 2>/dev/null || true
fi
