#!/usr/bin/env python3
"""
Stop hook check — called by on-stop.sh before sending the notification.

If the current task is still in-progress, blocks the stop ONCE and
asks the agent to update the task before the session closes.

Uses a flag file to avoid blocking more than once per session end sequence
(so if the agent can't update for some reason, it can still exit on the
second attempt).
"""
import json, os, sys, urllib.request

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, INSTALL_DIR)
from lib import session_task_file

BASE_URL = 'http://localhost:3456'


def main():
    branch = sys.argv[1] if len(sys.argv) > 1 else ''

    # Only check when we have a named, non-default branch
    if not branch or branch in ('HEAD', 'main', 'master', ''):
        return

    tf = session_task_file(branch)
    if not os.path.exists(tf):
        return  # No linked task for this session

    task_id = open(tf).read().strip()
    if not task_id:
        return

    # Flag file: written on first block, removed on second (allows through)
    flag = tf + '.stop-reminded'
    if os.path.exists(flag):
        try:
            os.remove(flag)
        except Exception:
            pass
        return  # Already reminded once — let the session end

    # Fetch all tasks and find this one
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = json.loads(r.read())
        task = next((t for t in tasks if t.get('id') == task_id), None)
        if not task:
            return  # Task not found (may have been deleted)
    except Exception:
        return  # Server unreachable — don't block

    status = task.get('status', '')
    if status not in ('in-progress', 'todo'):
        return  # Already updated — allow the stop

    title = task.get('title', task_id)

    # Write the flag so a second stop attempt goes through
    try:
        open(flag, 'w').close()
    except Exception:
        pass

    # Emit block decision — Claude Code shows this to the agent
    print(json.dumps({
        'decision': 'block',
        'reason': (
            f'Task "{title}" is still in-progress.\n\n'
            f'Please update it before finishing:\n\n'
            f'curl -s -X PATCH {BASE_URL}/tasks/{task_id} \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -d \'{{"status":"in-review",'
            f'"notes":"Done: ...\\nNext: ...",'
            f'"prLinks":[{{"url":"<PR>","label":"<repo #N>"}}],'
            f'"claimedBy":"","lastUpdated":"<ISO>"}}\'\n\n'
            f'If still in progress, update notes with current state and set claimedBy: "".'
        ),
    }))


if __name__ == '__main__':
    main()
