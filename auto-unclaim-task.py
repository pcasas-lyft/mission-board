#!/usr/bin/env python3
"""
WorktreeRemove hook — clears claimedBy on any task that was claimed
by the branch associated with the removed worktree.
Also removes the session task file written by auto-claim-task.py.
"""
import json, sys, os, urllib.request, urllib.error
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import session_task_file

BASE_URL = 'http://localhost:3456'


def get_branch(data):
    for key in ('branch', 'worktree_branch'):
        if data.get(key):
            return data[key]
    tool_input = data.get('tool_input', {})
    for key in ('branch', 'worktree_branch'):
        if tool_input.get(key):
            return tool_input[key]
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    branch = get_branch(data)
    if not branch:
        sys.exit(0)

    # Remove the session task file
    try:
        tf = session_task_file(branch)
        if os.path.exists(tf):
            os.remove(tf)
    except Exception:
        pass

    # Fetch all tasks
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as resp:
            tasks = json.loads(resp.read())
    except Exception:
        sys.exit(0)

    # Find any task claimed by this branch and clear the claim
    claimed = [t for t in tasks if t.get('claimedBy') == branch]
    if not claimed:
        sys.exit(0)

    for task in claimed:
        patch = {
            'claimedBy': '',
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
        }
        body = json.dumps(patch).encode()
        req = urllib.request.Request(
            f'{BASE_URL}/tasks/{task["id"]}',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='PATCH',
        )
        try:
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            pass


if __name__ == '__main__':
    main()
