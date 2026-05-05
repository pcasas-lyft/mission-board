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

def slug_words(branch):
    segment = branch.split('/')[-1]
    return [w.lower() for w in segment.split('-') if len(w) >= 4]

def slug_match_score(words, title):
    title_lower = title.lower()
    return sum(1 for w in words if w in title_lower)

def find_task_by_slug(tasks, branch):
    words = slug_words(branch)
    if len(words) < 2:
        return None

    scored = [(slug_match_score(words, t.get('title', '')), t)
              for t in tasks if not t.get('done')]
    scored.sort(key=lambda x: -x[0])

    if not scored or scored[0][0] < 2:
        return None

    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None

    return scored[0][1]

def main():
    path   = sys.argv[1] if len(sys.argv) > 1 else 'tasks.json'
    branch = sys.argv[2].strip() if len(sys.argv) > 2 else ''

    try:
        with open(path) as f:
            tasks = json.load(f)
    except Exception:
        print('Could not read tasks')
        return

    task = None
    if branch and branch not in ('HEAD', 'main', 'master', ''):
        # Strategy 1: explicit claimedBy match
        task = next((t for t in tasks if t.get('claimedBy') == branch), None)

        # Strategy 2: slug match for user-prefixed or description-only branches
        if not task:
            task = find_task_by_slug(tasks, branch)

    if not task:
        print("Session ended — no task linked\nOpen tracker to update status")
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
        'done':        'Done',
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
