#!/bin/bash
# Stop hook — runs every time a Claude Code agent session ends.
#
# Flow:
#   1. If the linked task is still in-progress, block the stop ONCE and
#      ask the agent to update it (stop-check.py emits a block decision).
#   2. Otherwise: archive old done tasks, regenerate docs, clear stale
#      claim, send Mac notification.

DIR="$(dirname "$0")"
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# ── 1. Possibly block the stop ───────────────────────────────────────────────
STOP_CHECK=$(python3 "$DIR/stop-check.py" "$BRANCH" 2>/dev/null)
if [[ -n "$STOP_CHECK" ]]; then
    echo "$STOP_CHECK"   # Claude Code reads this — contains {"decision":"block",...}
    exit 0
fi

# ── 2. Session is ending — run maintenance tasks ─────────────────────────────
python3 "$DIR/archive-tasks.py"  2>/dev/null
python3 "$DIR/gen-status.py"     2>/dev/null
python3 "$DIR/gen-donelog.py"    2>/dev/null

# ── 3. Clear stale claim for this branch ────────────────────────────────────
# (WorktreeRemove also does this, but not all sessions use worktrees)
echo '{}' | python3 "$DIR/auto-unclaim-task.py" 2>/dev/null

# ── 4. Send notification ─────────────────────────────────────────────────────
SAFE_BRANCH="${BRANCH//\//-}"
TASK_ID_FILE="${TMPDIR:-/tmp}/claude-task-${SAFE_BRANCH}.id"
NOTIF=$(python3 "$DIR/notif-summary.py" "$DIR/tasks.json" "$BRANCH" "$TASK_ID_FILE" 2>/dev/null)

if [[ -n "$NOTIF" ]]; then
    if command -v terminal-notifier &>/dev/null; then
        terminal-notifier \
            -title "Agent Done 🤖" \
            -message "$NOTIF" \
            -open "http://localhost:3456" \
            -sound Glass 2>/dev/null || true
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        osascript -e "display notification \"$NOTIF\" with title \"Agent Done 🤖\" sound name \"Glass\"" 2>/dev/null || true
    fi
fi
