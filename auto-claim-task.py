#!/usr/bin/env python3
"""
WorktreeCreate hook — reads the branch name from stdin JSON,
extracts a task ID using the naming convention, and PATCHes
that task to in-progress + sets claimedBy.

Also writes a temp file (/tmp/claude-task-<branch>.id) so that
on-stop.sh can reliably identify which task this session owned
without guessing from branch names.

Branch naming convention:
  feat/<task-id>-description   e.g. feat/t4-tcs-mcp     → task id: t4
  fix/<task-id>-description    e.g. fix/1746001234-bug   → task id: 1746001234

Fallback for user-prefixed branches (e.g. alice/promo-banner-redesign):
  Slug-matches branch description against task titles.

If the branch doesn't match or the task isn't found, exits silently.
"""
import json, sys, re, os, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import find_task_by_slug, session_task_file, write_session_tasks

BASE_URL = 'http://localhost:3456'


def get_branch(data):
    for key in ('branch', 'worktree_branch'):
        if data.get(key):
            return data[key]
    tool_input = data.get('tool_input', {})
    for key in ('branch', 'worktree_branch'):
        if tool_input.get(key):
            return tool_input[key]

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

    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as resp:
            tasks = json.loads(resp.read())
    except Exception:
        sys.exit(0)

    # Strategy 1: task ID encoded in branch name (feat/t4-name, fix/1234-name)
    task_id = extract_task_id(branch)
    task = next((t for t in tasks if t.get('id') == task_id), None)

    # Strategy 2: slug match for user-prefixed branches (alice/*, bob/*, etc.)
    # NOTE: claimedBy lookup intentionally removed — claimedBy is no longer a lock
    # and stale values caused wrong tasks to be injected into unrelated sessions.
    if not task:
        task = find_task_by_slug(tasks, branch)

    if not task:
        sys.exit(0)

    task_id = task.get('id')

    # Don't lock — multiple agents can work on the same task.
    # Only set status to in-progress; don't touch claimedBy.
    patch = {
        'status': 'in-progress',
        'done': False,
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

    # Write session task file (array format) so stop hook can find all tasks
    try:
        write_session_tasks(branch, [task_id])
    except Exception:
        pass

    print(json.dumps({
        'systemMessage': (
            f'Auto-claimed task "{task["title"]}" (id: {task_id}) '
            f'from branch {branch}. Status set to in-progress. '
            f'Update it via PATCH {BASE_URL}/tasks/{task_id} when done.'
        )
    }))


if __name__ == '__main__':
    main()
