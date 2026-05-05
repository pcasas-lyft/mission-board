#!/usr/bin/env python3
"""
WorktreeCreate hook — reads the branch name from stdin JSON,
extracts a task ID using the naming convention, and PATCHes
that task to in-progress + sets claimedBy.

Branch naming convention:
  feat/<task-id>-description   e.g. feat/t4-tcs-mcp     → task id: t4
  fix/<task-id>-description    e.g. fix/1746001234-bug   → task id: 1746001234

If the branch doesn't match or the task isn't found, exits silently.
"""
import json, sys, re, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone

BASE_URL = 'http://localhost:3456'

def get_branch(data):
    # Try hook input fields first
    for key in ('branch', 'worktree_branch'):
        if data.get(key):
            return data[key]
    tool_input = data.get('tool_input', {})
    for key in ('branch', 'worktree_branch'):
        if tool_input.get(key):
            return tool_input[key]

    # Fall back to git
    try:
        r = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None

def extract_task_id(branch):
    # Take the last path segment, grab up to the first '-'
    # feat/t4-tcs-mcp → "t4-tcs-mcp" → "t4"
    segment = branch.split('/')[-1]
    m = re.match(r'^([a-zA-Z0-9]+)(?:-|$)', segment)
    return m.group(1) if m else None

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    branch = get_branch(data)
    if not branch or branch in ('HEAD', 'main', 'master'):
        sys.exit(0)

    task_id = extract_task_id(branch)
    if not task_id:
        sys.exit(0)

    # Fetch all tasks and find the matching one
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as resp:
            tasks = json.loads(resp.read())
    except Exception:
        sys.exit(0)

    task = next((t for t in tasks if t.get('id') == task_id), None)
    if not task:
        sys.exit(0)

    # PATCH: claim the task and set in-progress
    patch = {
        'status': 'in-progress',
        'done': False,
        'claimedBy': branch,
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(patch).encode()
    req = urllib.request.Request(
        f'{BASE_URL}/tasks/{task_id}',
        data=body,
        headers={'Content-Type': 'application/json'},
        method='PATCH',
    )
    try:
        with urllib.request.urlopen(req, timeout=3):
            pass
    except Exception:
        sys.exit(0)

    # Inject a systemMessage so Claude knows what task it's on
    print(json.dumps({
        'systemMessage': (
            f'Auto-claimed task "{task["title"]}" (id: {task_id}) '
            f'from branch {branch}. Status set to in-progress. '
            f'Update it via PATCH {BASE_URL}/tasks/{task_id} when done.'
        )
    }))

if __name__ == '__main__':
    main()
