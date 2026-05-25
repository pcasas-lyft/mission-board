#!/bin/bash
# Stop hook — runs every time a Claude Code agent session ends.
#
# Flow:
#   1. If any linked task is still in-progress, block the stop ONCE and
#      ask the agent to log progress via the todo-tracker MCP tools.
#   2. Otherwise: archive old done tasks, regenerate docs, send notification.

DIR="$(dirname "$0")"

# ── Collect branches from ALL git repos under ~/src/ ─────────────────────────
# Claude sessions often span multiple repos (e.g. instant-android + membershipsapi).
# Using only the CWD branch misses tasks linked to other repos' branches.
declare -A SEEN_BRANCHES
ALL_BRANCHES=()
for REPO in "$HOME/src"/*/; do
    if git -C "$REPO" rev-parse --git-dir > /dev/null 2>&1; then
        B=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)
        if [[ -n "$B" && "$B" != "HEAD" && "$B" != "main" && "$B" != "master" ]]; then
            if [[ -z "${SEEN_BRANCHES[$B]+x}" ]]; then
                SEEN_BRANCHES[$B]=1
                ALL_BRANCHES+=("$B")
            fi
        fi
    fi
done

# Primary branch (CWD) for backward-compat fallback
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# ── 1. Possibly block the stop ───────────────────────────────────────────────
STOP_CHECK=$(python3 "$DIR/stop-check.py" "${ALL_BRANCHES[@]}" 2>/dev/null)
if [[ -n "$STOP_CHECK" ]]; then
    echo "$STOP_CHECK"   # Claude Code reads this — contains {"decision":"block",...}
    exit 0
fi

# ── 2. Session is ending — run maintenance tasks ─────────────────────────────
python3 "$DIR/archive-tasks.py"  2>/dev/null
python3 "$DIR/gen-status.py"     2>/dev/null
python3 "$DIR/gen-donelog.py"    2>/dev/null

# ── 3. Send notification — pass ALL branches; notif-summary aggregates them ──
NOTIF=$(python3 "$DIR/notif-summary.py" "$DIR/tasks.json" "${ALL_BRANCHES[@]}" 2>/dev/null)

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
