#!/usr/bin/env python3
"""
SessionStart hook — injects live work status into every agent session.

1. Reads WORKSTATUS.md and includes it as the systemMessage.
2. Scans ALL git repos under ~/src/ for active branches and auto-claims
   matching tasks (not just the CWD branch — sessions span multiple repos).
3. Highlights all session tasks across all repos.
4. If on main in all repos, lists active worktrees for context.
"""
import json, os, sys, subprocess, urllib.request, glob, tempfile

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.normpath(os.path.join(INSTALL_DIR, '..', 'WORKSTATUS.md'))
BASE_URL = 'http://localhost:3456'
SRC_DIR = os.path.expanduser('~/src')

sys.path.insert(0, INSTALL_DIR)
from lib import read_session_tasks, session_task_file, write_session_tasks


def get_all_branches():
    """
    Return all active non-main branches across every git repo in ~/src/.
    Sessions routinely span multiple repos (e.g. instant-android + membershipsapi),
    so restricting to the CWD branch misses most of the real work.
    Returns a deduplicated list, CWD branch first if present.
    """
    branches = {}  # branch → repo path (first seen wins for dedup)

    # CWD branch first for backward-compat (stop hook flag files use CWD branch)
    try:
        r = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            b = r.stdout.strip()
            if b and b not in ('HEAD', 'main', 'master'):
                branches[b] = '.'
    except Exception:
        pass

    # All repos under ~/src/
    if os.path.isdir(SRC_DIR):
        for entry in os.scandir(SRC_DIR):
            if not entry.is_dir():
                continue
            try:
                r = subprocess.run(
                    ['git', '-C', entry.path, 'rev-parse', '--abbrev-ref', 'HEAD'],
                    capture_output=True, text=True, timeout=3,
                )
                b = r.stdout.strip()
                if b and b not in ('HEAD', 'main', 'master') and r.returncode == 0:
                    branches.setdefault(b, entry.path)
            except Exception:
                pass

    return list(branches.keys())


def auto_claim_all(branches):
    """Run auto-claim for every branch found across all repos."""
    script = os.path.join(INSTALL_DIR, 'auto-claim-task.py')
    for branch in branches:
        try:
            subprocess.run(
                ['python3', script],
                input=json.dumps({'branch': branch}),
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
        if path and branch and branch not in ('main', 'master'):
            worktrees[branch] = path
        return worktrees
    except Exception:
        return {}


def collect_session_task_ids(branches):
    """Aggregate task IDs from session files across all active branches."""
    seen = set()
    task_ids = []
    for branch in branches:
        for tid in read_session_tasks(branch):
            if tid not in seen:
                seen.add(tid)
                task_ids.append(tid)
    return task_ids


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
    Uses session task files (not claimedBy) to match branches to tasks.
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
        branch_task_ids = read_session_tasks(branch)
        branch_tasks = [t for t in tasks if t.get('id') in branch_task_ids]

        if branch_tasks:
            for task in branch_tasks:
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


def prune_stale_session_files():
    """
    Clear session task files whose tasks are all fully done.
    Only prunes 'done' — not 'in-review', because in-review tasks should
    still trigger a notification when the session ends.
    """
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = {t['id']: t for t in json.loads(r.read())}
    except Exception:
        return

    pattern = os.path.join(tempfile.gettempdir(), 'claude-task-*.id')
    for path in glob.glob(pattern):
        try:
            content = open(path).read().strip()
            if not content:
                os.remove(path)
                continue
            ids = json.loads(content) if content.startswith('[') else [content]
            if ids and all(tasks.get(tid, {}).get('status') == 'done' for tid in ids):
                os.remove(path)
        except Exception:
            pass


def main():
    branches = get_all_branches()
    prune_stale_session_files()
    auto_claim_all(branches)

    # on_main = no non-main branches found anywhere
    on_main = len(branches) == 0
    worktrees = get_worktrees()

    status = load_status()
    task_ids = collect_session_task_ids(branches)
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
        "want me to continue from that? It has a worktree at [path].\"\n"
        "3. If yes: use absolute paths to that worktree for all file reads, "
        "edits, and git commands (e.g. cd [path] && git status). "
        "Link the task: python3 " + INSTALL_DIR + "/add-session-task.py <id>\n"
        "   Multiple agents can work on the same task — no locking.\n"
        "4. If no match or new work: create_task first, then proceed.\n"
        "5. For branch-level work under an existing task, create a child task\n"
        "   (same project, descriptive title) rather than reusing the parent."
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
        "Tasks are shared ledgers — multiple agents/branches can contribute.\n"
        "Log progress to the most specific task for your work (child task if one exists).\n\n"
        "When finishing work, update_task with:\n"
        '  status="in-review", notes="Done: ...\\nNext: ...",\n'
        '  pr_links=[{"url":"https://github.com/…","label":"repo #N"}]\n\n'
        "If work is ongoing and another agent may continue, update notes with\n"
        "current state so they have full context.\n\n"
        "Multi-task sessions: if you pivot to new work mid-session, check\n"
        "list_tasks for a match and ask the user before linking it:\n"
        f"  python3 {INSTALL_DIR}/add-session-task.py <id>"
    )

    print(json.dumps({"systemMessage": '\n\n'.join(parts)}))


if __name__ == '__main__':
    main()
