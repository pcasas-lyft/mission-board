#!/usr/bin/env python3
"""
Stop hook check — called by on-stop.sh before sending the notification.

If any session task is still in-progress or todo, blocks the stop ONCE and
asks the agent to update all of them before the session closes.

Uses a flag file to avoid blocking more than once per session end sequence.
"""
import json, os, sys, subprocess, urllib.request

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, INSTALL_DIR)
from lib import session_task_file, read_session_tasks

BASE_URL = 'http://localhost:3456'


def get_branch_fallback():
    """Fallback: detect branch via git when not passed as argument."""
    try:
        r = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ''


def main():
    # Accept multiple branches (one per argv) — collect task IDs across all of them.
    branches = [b for b in sys.argv[1:] if b and b not in ('HEAD', 'main', 'master')]

    if not branches:
        branch = get_branch_fallback()
        if branch and branch not in ('HEAD', 'main', 'master', ''):
            branches = [branch]

    if not branches:
        return

    task_ids = []
    for branch in branches:
        task_ids.extend(read_session_tasks(branch))
    task_ids = list(dict.fromkeys(task_ids))  # deduplicate, preserve order

    if not task_ids:
        return

    # Flag file: use the first branch as the key (consistent across calls)
    branch = branches[0]
    # Flag file: block once, then let through on second attempt
    flag = session_task_file(branch) + '.stop-reminded'
    if os.path.exists(flag):
        try:
            os.remove(flag)
        except Exception:
            pass
        return  # Already reminded once — let the session end

    # Fetch all tasks
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = json.loads(r.read())
    except Exception:
        return  # Server unreachable — don't block

    # Find session tasks that still need an update
    pending = []
    for tid in task_ids:
        task = next((t for t in tasks if t.get('id') == tid), None)
        if task and task.get('status') in ('in-progress', 'todo'):
            pending.append(task)

    if not pending:
        return  # All tasks already updated — allow the stop

    # Write flag so second stop attempt goes through
    try:
        open(flag, 'w').close()
    except Exception:
        pass

    task_word = 'task' if len(pending) == 1 else 'tasks'
    titles = ', '.join(f'"{t["title"]}"' for t in pending)
    task_lines = []
    for t in pending:
        task_lines.append(
            f'• "{t["title"]}" (id: {t["id"]})\n'
            f'  → Use the todo-tracker MCP tool: update_task\n'
            f'    id="{t["id"]}", status="in-review",\n'
            f'    notes="Done: <what you did>\\nNext: <next step>",\n'
            f'    pr_links=[{{"url":"<PR>","label":"<repo #N>"}}]'
        )

    print(json.dumps({
        'decision': 'block',
        'reason': (
            f'Please log progress on {len(pending)} {task_word} before finishing:\n\n'
            + '\n\n'.join(task_lines)
            + '\n\nCall update_task via the todo-tracker MCP server for each task above.'
            + '\nIf work is ongoing, leave notes so the next agent has full context.'
        ),
    }))


if __name__ == '__main__':
    main()
