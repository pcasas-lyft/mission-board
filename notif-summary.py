#!/usr/bin/env python3
"""
Notification message for the agent that just stopped.
Shows details about the specific task this agent was working on.
If the branch isn't linked to a task, says so — doesn't show unrelated tasks.

Usage: python3 notif-summary.py <tasks.json> [current-branch]
"""
import json, sys

def trunc(s, n=36):
    return s if len(s) <= n else s[:n - 1] + '…'

def main():
    path   = sys.argv[1] if len(sys.argv) > 1 else 'tasks.json'
    branch = sys.argv[2].strip() if len(sys.argv) > 2 else ''

    try:
        with open(path) as f:
            tasks = json.load(f)
    except Exception:
        print('Could not read tasks')
        return

    # Find the task this agent was working on
    task = None
    if branch and branch not in ('HEAD', 'main', 'master', ''):
        task = next((t for t in tasks if t.get('claimedBy') == branch), None)

    if not task:
        # No task linked — just acknowledge the session ended, no noise
        print("Session ended — no task linked\nOpen tracker to update status")
        return

    # Show what happened to that specific task
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
        'done':        'Done',
    }.get(task.get('status', ''), task.get('status', 'Updated'))

    lines = [f"{status_icon} {status_label}: {trunc(task['title'])}"]

    if task.get('blockedOn'):
        lines.append(f"Waiting on: {trunc(task['blockedOn'], 40)}")

    if task.get('prLink'):
        lines.append(f"PR: {trunc(task['prLink'], 40)}")

    # Show last note line if there is one
    notes = (task.get('notes') or '').strip()
    if notes:
        last_line = [l.strip() for l in notes.splitlines() if l.strip()][-1]
        if last_line:
            lines.append(trunc(last_line, 50))

    print('\n'.join(lines))

if __name__ == '__main__':
    main()
