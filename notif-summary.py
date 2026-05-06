#!/usr/bin/env python3
"""
Notification message for the agent that just stopped.
Shows details about the specific task this agent was working on.

Resolution order:
  1. task_id_file  — path to a temp file written by auto-claim-task.py
                     containing the task ID for the branch (most reliable)
  2. claimedBy     — explicit branch→task link already on the task object
  3. slug match    — fuzzy match against branch name (fallback, can miss)

If nothing resolves, prints nothing — no notification fires.

Usage: python3 notif-summary.py <tasks.json> [branch] [task_id_file]
"""
import json, os, sys

# Add the tracker directory to the path so we can import lib.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import find_task_by_slug


def trunc(s, n=36):
    return s if len(s) <= n else s[:n - 1] + '…'


def main():
    path         = sys.argv[1] if len(sys.argv) > 1 else 'tasks.json'
    branch       = sys.argv[2].strip() if len(sys.argv) > 2 else ''
    task_id_file = sys.argv[3] if len(sys.argv) > 3 else ''

    try:
        with open(path) as f:
            tasks = json.load(f)
    except Exception:
        return  # silent — server may be down

    task = None

    # Strategy 1: explicit session→task file written by auto-claim-task.py
    if task_id_file and os.path.exists(task_id_file):
        try:
            task_id = open(task_id_file).read().strip()
            task = next((t for t in tasks if t.get('id') == task_id), None)
        except Exception:
            pass

    # Strategy 2: claimedBy still set on the task
    if not task and branch and branch not in ('HEAD', 'main', 'master', ''):
        task = next((t for t in tasks if t.get('claimedBy') == branch), None)

    # Strategy 3: slug match (only fires when no explicit link was found)
    if not task and branch and branch not in ('HEAD', 'main', 'master', ''):
        task = find_task_by_slug(tasks, branch)

    # No reliable match — stay silent rather than show wrong task
    if not task:
        return

    status_icon = {
        'in-progress': '🟡',
        'in-review':   '🔄',
        'blocked':     '⛔',
        'done':        '✅',
    }.get(task.get('status', ''), '•')

    status_label = {
        'in-progress': 'Still in progress',
        'in-review':   'In review',
        'blocked':     'Blocked',
        'done':        'Done ✓',
    }.get(task.get('status', ''), task.get('status', 'Updated'))

    lines = [f"{status_icon} {status_label}: {trunc(task['title'])}"]

    if task.get('blockedOn'):
        lines.append(f"Waiting on: {trunc(task['blockedOn'], 40)}")

    notes = (task.get('notes') or '').strip()
    if notes:
        last_line = [l.strip() for l in notes.splitlines() if l.strip()][-1]
        if last_line:
            lines.append(trunc(last_line, 50))

    print('\n'.join(lines))


if __name__ == '__main__':
    main()
