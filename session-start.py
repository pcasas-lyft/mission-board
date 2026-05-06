#!/usr/bin/env python3
"""
SessionStart hook — injects live work status into every agent session.

1. Reads WORKSTATUS.md and includes it as the systemMessage so agents
   start with full situational awareness without needing to read a file.
2. Attempts to auto-claim the task for the current branch (handles the
   case where a session starts on an existing branch without a new
   WorktreeCreate event).
"""
import json, os, sys, subprocess

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.normpath(os.path.join(INSTALL_DIR, '..', 'WORKSTATUS.md'))


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
    """Run auto-claim-task.py for this branch (idempotent — safe to call again)."""
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
    # Strip the boilerplate Agent API Reference section at the bottom
    divider = '\n---\n'
    if divider in content:
        content = content[:content.index(divider)].strip()
    return content


def main():
    branch = get_branch()

    # Auto-claim in the background for non-main branches
    try_auto_claim(branch)

    status = load_status()

    msg = (
        f"{status}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK TRACKER  http://localhost:3456\n"
        "  PATCH /tasks/<id>          — update status, notes, claimedBy\n"
        "  PATCH /tasks/<id>/log      — append a progress log entry\n"
        "  POST  /tasks/new           — create a task if none exists\n"
        "  DELETE /tasks/<id>         — remove a task\n\n"
        "When finishing work, PATCH with:\n"
        '  {"status":"in-review","notes":"Done: ...\\nNext: ...",\n'
        '   "prLinks":[{"url":"https://github.com/…","label":"repo #N"}],\n'
        '   "claimedBy":"","lastUpdated":"<ISO timestamp>"}'
    )

    print(json.dumps({"systemMessage": msg}))


if __name__ == '__main__':
    main()
