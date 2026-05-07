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
from lib import read_session_tasks


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

    session_tasks = []

    # Strategy 1: session file (new array format or legacy single ID)
    if task_id_file and os.path.exists(task_id_file):
        try:
            task_ids = read_session_tasks(branch) if branch else []
            # Fallback: read the file directly if read_session_tasks returns nothing
            if not task_ids:
                raw = open(task_id_file).read().strip()
                import json as _j
                task_ids = _j.loads(raw) if raw.startswith('[') else ([raw] if raw else [])
            session_tasks = [t for t in tasks if t.get('id') in task_ids]
        except Exception:
            pass

    # Strategy 2: claimedBy
    if not session_tasks and branch and branch not in ('HEAD', 'main', 'master', ''):
        claimed = [t for t in tasks if t.get('claimedBy') == branch]
        if claimed:
            session_tasks = claimed

    if not session_tasks:
        return  # No reliable match — stay silent

    STATUS_ICON  = {'in-progress':'🟡','in-review':'🔄','blocked':'⛔','done':'✅'}
    STATUS_LABEL = {'in-progress':'Still in progress','in-review':'In review',
                    'blocked':'Blocked','done':'Done ✓'}

    if len(session_tasks) == 1:
        task = session_tasks[0]
        icon  = STATUS_ICON.get(task.get('status', ''), '•')
        label = STATUS_LABEL.get(task.get('status', ''), task.get('status', 'Updated'))
        lines = [f"{icon} {label}: {trunc(task['title'])}"]
        if task.get('blockedOn'):
            lines.append(f"Waiting on: {trunc(task['blockedOn'], 40)}")
        notes = (task.get('notes') or '').strip()
        if notes:
            last_line = [l.strip() for l in notes.splitlines() if l.strip()][-1]
            if last_line:
                lines.append(trunc(last_line, 50))
    else:
        # Multi-task session summary
        summary_parts = []
        for t in session_tasks:
            icon = STATUS_ICON.get(t.get('status', ''), '•')
            summary_parts.append(f"{icon} {trunc(t['title'], 28)}")
        lines = [f"{len(session_tasks)} tasks this session:"] + summary_parts

    print('\n'.join(lines))


if __name__ == '__main__':
    main()
