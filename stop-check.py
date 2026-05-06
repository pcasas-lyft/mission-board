#!/usr/bin/env python3
"""
Stop hook check — called by on-stop.sh before sending the notification.

If any session task is still in-progress or todo, blocks the stop ONCE and
asks the agent to update all of them before the session closes.

Uses a flag file to avoid blocking more than once per session end sequence.
"""
import json, os, sys, urllib.request

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, INSTALL_DIR)
from lib import session_task_file, read_session_tasks

BASE_URL = 'http://localhost:3456'


def main():
    branch = sys.argv[1] if len(sys.argv) > 1 else ''

    if not branch or branch in ('HEAD', 'main', 'master', ''):
        return

    task_ids = read_session_tasks(branch)
    if not task_ids:
        return

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
    curls = []
    for t in pending:
        curls.append(
            f'# {t["title"]} ({t["id"]})\n'
            f'curl -s -X PATCH {BASE_URL}/tasks/{t["id"]} \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -d \'{{"status":"in-review",'
            f'"notes":"Done: ...\\nNext: ...",'
            f'"prLinks":[{{"url":"<PR>","label":"<repo #N>"}}],'
            f'"claimedBy":"","lastUpdated":"<ISO>"}}\''
        )

    print(json.dumps({
        'decision': 'block',
        'reason': (
            f'{len(pending)} {task_word} still in-progress: {titles}\n\n'
            f'Please update before finishing:\n\n'
            + '\n\n'.join(curls)
            + '\n\nIf still in progress, update notes with current state and set claimedBy: "".'
        ),
    }))


if __name__ == '__main__':
    main()
