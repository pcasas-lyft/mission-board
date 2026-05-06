#!/usr/bin/env python3
"""
Add a task to the current session mid-flight.

Called by agents when the user pivots to a second piece of work within
the same chat. Links the task to the session file so the stop hook tracks
it and prompts for an update when the session ends.

Usage: python3 add-session-task.py <task_id>
"""
import json, os, sys, subprocess, urllib.request
from datetime import datetime, timezone

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, INSTALL_DIR)
from lib import read_session_tasks, write_session_tasks

BASE_URL = 'http://localhost:3456'


def get_branch():
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
    if len(sys.argv) < 2:
        print('Usage: add-session-task.py <task_id>', file=sys.stderr)
        sys.exit(1)

    task_id = sys.argv[1].strip()
    branch  = get_branch()
    if not branch:
        print('Could not determine current branch.', file=sys.stderr)
        sys.exit(1)

    # Validate task exists
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = json.loads(r.read())
        task = next((t for t in tasks if t.get('id') == task_id), None)
    except Exception as e:
        print(f'Could not reach task tracker: {e}', file=sys.stderr)
        sys.exit(1)

    if not task:
        print(f'Task "{task_id}" not found.', file=sys.stderr)
        sys.exit(1)

    # Deduplicate and append
    current = read_session_tasks(branch)
    if task_id in current:
        print(f'Task "{task["title"]}" is already linked to this session.')
        sys.exit(0)

    write_session_tasks(branch, current + [task_id])

    # Patch to in-progress + claimedBy if not already
    needs_patch = (
        task.get('status') not in ('in-progress',) or
        task.get('claimedBy') != branch
    )
    if needs_patch:
        patch = {
            'status':      'in-progress',
            'claimedBy':   branch,
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
        }
        req = urllib.request.Request(
            f'{BASE_URL}/tasks/{task_id}',
            data=json.dumps(patch).encode(),
            headers={'Content-Type': 'application/json'},
            method='PATCH',
        )
        try:
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception as e:
            print(f'Warning: could not patch task: {e}', file=sys.stderr)

    all_ids = current + [task_id]
    print(f'✓ Linked "{task["title"]}" to this session.')
    print(f'  Session now tracks {len(all_ids)} task{"s" if len(all_ids) != 1 else ""}: {", ".join(all_ids)}')


if __name__ == '__main__':
    main()
