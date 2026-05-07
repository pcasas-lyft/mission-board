#!/usr/bin/env python3
"""
SessionStart hook — injects live work status into every agent session.

1. Reads WORKSTATUS.md and includes it as the systemMessage.
2. Auto-claims the task for the current branch (non-main branches).
3. If already on a task branch, highlights the session tasks explicitly.
4. If on main, lists all active worktrees so the agent can work via
   absolute paths and proactively match the user's prompt to a task.
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


def get_worktrees():
    """Returns {branch: path} for all git worktrees except main."""
    try:
        r = subprocess.run(
            ['git', 'worktree', 'list', '--porcelain'],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return {}
        worktrees = {}
        path = branch = None
        for line in r.stdout.splitlines():
            if line.startswith('worktree '):
                path = line[9:].strip()
            elif line.startswith('branch refs/heads/'):
                branch = line[len('branch refs/heads/'):].strip()
            elif line == '':
                if path and branch and branch not in ('main', 'master'):
                    worktrees[branch] = path
                path = branch = None
        # catch last block if no trailing newline
        if path and branch and branch not in ('main', 'master'):
            worktrees[branch] = path
        return worktrees
    except Exception:
        return {}


def load_session_context(task_ids, worktrees):
    """Return a context block for all tasks linked to this session."""
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
        claimed = t.get('claimedBy', '')
        if claimed and claimed in worktrees:
            lines.append(f'  📁 worktree: {worktrees[claimed]}')
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


def load_worktree_context(worktrees):
    """
    When on main: list all active worktrees cross-referenced with tasks.
    This lets the agent work via absolute paths without needing to cd.
    """
    if not worktrees:
        return ''
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = json.loads(r.read())
    except Exception:
        return ''

    lines = ['━━━ ACTIVE WORKTREES (you are on main) ━━━']
    for branch, path in worktrees.items():
        task = next((t for t in tasks if t.get('claimedBy') == branch), None)
        if task:
            status = task.get('status', 'todo')
            lines.append(f'• [{status.upper()}] {task["title"]}')
            lines.append(f'  id:     {task["id"]}')
            lines.append(f'  branch: {branch}')
            lines.append(f'  path:   {path}')
        else:
            lines.append(f'• {branch}  →  {path}  (no linked task)')

    if len(lines) == 1:
        return ''
    return '\n'.join(lines)


def main():
    branch = get_branch()
    try_auto_claim(branch)

    on_main = branch in ('main', 'master', '')
    worktrees = get_worktrees()

    status = load_status()
    task_ids = read_session_tasks(branch)
    session_ctx = load_session_context(task_ids, worktrees)
    worktree_ctx = load_worktree_context(worktrees) if on_main else ''

    parts = [status]
    if session_ctx:
        parts.append(session_ctx)
    if worktree_ctx:
        parts.append(worktree_ctx)

    main_branch_instructions = (
        "\n⚠️  YOU ARE ON MAIN — before doing any work:\n"
        "1. Call search_tasks with keywords from the user's request.\n"
        "2. If a match is found, say: \"This looks like [task title] — "
        "want me to continue from that task? It has a worktree at [path].\"\n"
        "3. If yes: use absolute paths to that worktree for all file reads, "
        "edits, and git commands (e.g. cd [path] && git status). "
        "Link the task with: python3 " + INSTALL_DIR + "/add-session-task.py <id>\n"
        "4. If no: create a new task with create_task, then proceed.\n"
        "5. If no match: ask the user what they're working on before starting."
    ) if on_main else ''

    parts.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK TRACKER — use the todo-tracker MCP tools (preferred over curl):\n"
        "  list_tasks          — see all tasks (filter by status)\n"
        "  search_tasks        — find a task by keyword\n"
        "  get_task            — full detail for one task\n"
        "  create_task         — add a task if none exists\n"
        "  update_task         — change status, notes, prLinks, claimedBy\n"
        + main_branch_instructions + "\n\n"
        "When finishing work, update_task with:\n"
        '  status="in-review", notes="Done: ...\\nNext: ...",\n'
        '  prLinks=[{"url":"https://github.com/…","label":"repo #N"}],\n'
        '  claimedBy=""\n\n'
        "Multi-task sessions: if you pivot to new work mid-session, check\n"
        "list_tasks for a match and ask the user before linking it:\n"
        f"  python3 {INSTALL_DIR}/add-session-task.py <id>"
    )

    print(json.dumps({"systemMessage": '\n\n'.join(parts)}))


if __name__ == '__main__':
    main()
