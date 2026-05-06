#!/usr/bin/env python3
"""
SessionStart hook — injects live work status into every agent session.

1. Reads WORKSTATUS.md and includes it as the systemMessage.
2. Auto-claims the task for the current branch.
3. If multiple tasks are linked to this session, highlights them explicitly
   so the agent knows exactly what it's responsible for.
"""
import json, os, sys, subprocess, urllib.request

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.normpath(os.path.join(INSTALL_DIR, '..', 'WORKSTATUS.md'))
BASE_URL = 'http://localhost:3456'

sys.path.insert(0, INSTALL_DIR)
from lib import read_session_tasks


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


def try_auto_claim(branch):
    if not branch or branch in ('HEAD', 'main', 'master'):
        return
    script = os.path.join(INSTALL_DIR, 'auto-claim-task.py')
    try:
        subprocess.run(
            ['python3', script],
            input='{}',
            capture_output=True, text=True, timeout=8,
        )
    except Exception:
        pass


def load_status():
    if not os.path.exists(STATUS_FILE):
        return '(WORKSTATUS.md not found — tracker may not be running)'
    with open(STATUS_FILE) as f:
        content = f.read().strip()
    divider = '\n---\n'
    if divider in content:
        content = content[:content.index(divider)].strip()
    return content


def load_session_context(task_ids):
    """Return a brief context block for all tasks linked to this session."""
    if not task_ids:
        return ''
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = json.loads(r.read())
    except Exception:
        return ''

    session_tasks = [t for t in tasks if t.get('id') in task_ids]
    if not session_tasks:
        return ''

    lines = ['━━━ SESSION TASKS ━━━']
    for t in session_tasks:
        status = t.get('status', 'todo')
        lines.append(f'• [{status.upper()}] {t["title"]}  (id: {t["id"]})')
        if t.get('notes', '').strip():
            first = t['notes'].strip().splitlines()[0].strip()
            lines.append(f'  📌 {first}')
        prs = t.get('prLinks') or ([{'url': t['prLink'], 'label': 'PR'}] if t.get('prLink') else [])
        for p in prs:
            lines.append(f'  🔗 {p.get("label", "PR")}: {p["url"]}')
        docs = t.get('docs') or []
        for d in docs:
            lines.append(f'  📎 {d.get("title", d["url"])}: {d["url"]}')
    return '\n'.join(lines)


def main():
    branch = get_branch()
    try_auto_claim(branch)

    status = load_status()
    task_ids = read_session_tasks(branch)
    session_ctx = load_session_context(task_ids)

    parts = [status]
    if session_ctx:
        parts.append(session_ctx)

    parts.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK TRACKER  http://localhost:3456\n"
        "  PATCH /tasks/<id>          — update status, notes, claimedBy\n"
        "  PATCH /tasks/<id>/log      — append a progress log entry\n"
        "  POST  /tasks/new           — create a task if none exists\n"
        "  DELETE /tasks/<id>         — remove a task\n\n"
        "When finishing work, PATCH with:\n"
        '  {"status":"in-review","notes":"Done: ...\\nNext: ...",\n'
        '   "prLinks":[{"url":"https://github.com/…","label":"repo #N"}],\n'
        '   "claimedBy":"","lastUpdated":"<ISO timestamp>"}\n\n'
        "Multi-task sessions: if you pivot to new work mid-session, check\n"
        "GET /tasks for a match and ask the user before linking it:\n"
        '  python3 /Users/pcasas/src/todo-tracker/add-session-task.py <id>'
    )

    print(json.dumps({"systemMessage": '\n\n'.join(parts)}))


if __name__ == '__main__':
    main()
