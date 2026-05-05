#!/usr/bin/env python3
"""
Reads tasks.json and writes WORKSTATUS.md.
Run directly or via the Stop hook / fswatch watcher.
"""
import json, os, sys
from datetime import datetime, timezone

TASKS_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.json')
STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'WORKSTATUS.md')
STATUS_FILE = os.path.normpath(STATUS_FILE)

def load_tasks():
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE) as f:
        return json.load(f)

def fmt_date(iso):
    try:
        d = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return d.strftime('%b %-d')
    except Exception:
        return iso[:10] if iso else ''

def task_line(t, show_day=False):
    parts = [f"**{t['title']}**"]
    if show_day and t.get('day') and t['day'] != 'unscheduled':
        parts.append(f"— {fmt_date(t['day'] + 'T00:00:00')}")
    if t.get('prLink'):
        parts.append(f"· [PR/Branch]({t['prLink']})")
    if t.get('claimedBy'):
        parts.append(f"· 🔒 `{t['claimedBy']}`")
    line = ' '.join(parts)

    details = []
    if t.get('blockedOn'):
        details.append(f"  - ⛔ Blocked on: {t['blockedOn']}")
    if t.get('notes') and t['notes'].strip():
        for note_line in t['notes'].strip().splitlines():
            details.append(f"  - {note_line.strip()}")
    if t.get('subtasks'):
        pending = [s for s in t['subtasks'] if not s.get('done')]
        done_sts = [s for s in t['subtasks'] if s.get('done')]
        for s in pending:
            details.append(f"  - [ ] {s['text']}")
        for s in done_sts:
            details.append(f"  - [x] {s['text']}")

    return '- ' + line + ('\n' + '\n'.join(details) if details else '')

def main():
    tasks = load_tasks()
    now = datetime.now().strftime('%a %b %-d, %Y at %-I:%M %p')

    not_done     = [t for t in tasks if not t.get('done') and t.get('status') != 'done']
    done_tasks   = [t for t in tasks if t.get('done') or t.get('status') == 'done']

    # Ongoing band tasks (multi-day / this-week tasks)
    ongoing      = [t for t in not_done if t.get('ongoing')]
    active_now   = [t for t in ongoing if t.get('activeNow')]
    ongoing_idle = [t for t in ongoing if not t.get('activeNow')]

    # Day-scheduled and backlog tasks (not in ongoing band)
    day_tasks    = [t for t in not_done if not t.get('ongoing')]
    blocked      = [t for t in day_tasks if t.get('status') == 'blocked']
    in_review    = [t for t in day_tasks if t.get('status') == 'in-review']
    in_progress  = [t for t in day_tasks if t.get('status') == 'in-progress']
    scheduled    = [t for t in day_tasks if t.get('status') not in ('blocked', 'in-review', 'in-progress')
                    and t.get('day') and t['day'] != 'unscheduled']
    backlog      = [t for t in day_tasks if t.get('status') not in ('blocked', 'in-review', 'in-progress')
                    and t.get('day') == 'unscheduled']

    lines = [
        f"# Work Status",
        f"_Last updated: {now}_",
        f"_Tracker: http://localhost:3456 · `PATCH /tasks/<id>` to update a task_",
        "",
    ]

    if active_now:
        lines += ["## 🔴 Active Now", ""]
        for t in active_now:
            lines.append(task_line(t))
        lines.append("")

    if ongoing_idle:
        lines += ["## 🟣 This Week (Ongoing)", ""]
        for t in ongoing_idle:
            lines.append(task_line(t))
        lines.append("")

    if blocked:
        lines += ["## ⛔ Blocked", ""]
        for t in blocked:
            lines.append(task_line(t))
        lines.append("")

    if in_review:
        lines += ["## 🔄 In Review", ""]
        for t in in_review:
            lines.append(task_line(t))
        lines.append("")

    if in_progress:
        lines += ["## 🟡 In Progress", ""]
        for t in in_progress:
            lines.append(task_line(t))
        lines.append("")

    if scheduled:
        lines += ["## 📅 Scheduled This Week", ""]
        for t in sorted(scheduled, key=lambda t: t.get('day', '')):
            lines.append(task_line(t, show_day=True))
        lines.append("")

    if backlog:
        lines += ["## 📋 Backlog / Unscheduled", ""]
        for t in backlog:
            lines.append(task_line(t))
        lines.append("")

    if done_tasks:
        lines += ["## ✅ Done", ""]
        for t in done_tasks:
            lines.append(f"- ~~{t['title']}~~")
        lines.append("")

    lines += [
        "---",
        "",
        "## Agent API Reference",
        "",
        "**Base URL:** `http://localhost:3456`",
        "",
        "| Endpoint | Method | Purpose |",
        "|---|---|---|",
        "| `/tasks` | GET | Fetch all tasks |",
        "| `/tasks` | POST | Replace all tasks (use sparingly) |",
        "| `/tasks/<id>` | PATCH | Update a single task ← **use this** |",
        "",
        "**Status values:** `todo` · `in-progress` · `in-review` · `blocked` · `done`",
        "",
        "**When you finish work on a task, PATCH it with:**",
        "```json",
        '{',
        '  "status": "in-review",',
        '  "notes": "Done: X\\nNext: Y",',
        '  "prLink": "https://github.com/...",',
        '  "blockedOn": "",',
        '  "lastUpdated": "<ISO timestamp>"',
        '}',
        "```",
    ]

    output = '\n'.join(lines) + '\n'
    with open(STATUS_FILE, 'w') as f:
        f.write(output)

    print(f"✓ WORKSTATUS.md updated ({len(tasks)} tasks)", file=sys.stderr)

if __name__ == '__main__':
    main()
