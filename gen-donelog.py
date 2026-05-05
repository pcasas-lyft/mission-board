#!/usr/bin/env python3
"""
Reads completed tasks from tasks.json + tasks-archive.json
and writes DONELOG.md, grouped by week (most recent first).

Run directly or via on-stop.sh.
"""
import json, os, sys
from datetime import datetime, timezone, timedelta

INSTALL_DIR  = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE   = os.path.join(INSTALL_DIR, 'tasks.json')
ARCHIVE_FILE = os.path.join(INSTALL_DIR, 'tasks-archive.json')
DONELOG_FILE = os.path.normpath(os.path.join(INSTALL_DIR, '..', 'DONELOG.md'))


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        try:
            return json.load(f)
        except Exception:
            return []


def task_ts(t):
    """Return a datetime for sorting/grouping, preferring lastUpdated."""
    for key in ('lastUpdated', 'createdAt'):
        val = t.get(key)
        if val:
            try:
                dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
    return datetime.min.replace(tzinfo=timezone.utc)


def week_label(dt):
    """'Week of Mon May 5, 2026'"""
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime('Week of %a %b %-d, %Y')


def fmt_date(dt):
    return dt.strftime('%b %-d')


def task_line(t, dt):
    parts = [f"- ~~**{t['title']}**~~"]
    meta = [f"Completed {fmt_date(dt)}"]
    if t.get('jiraKey'):
        meta.append(f"[{t['jiraKey']}](https://jira.lyft.net/browse/{t['jiraKey']})")
    if t.get('prLink'):
        meta.append(f"[PR]({t['prLink']})")
    if t.get('claimedBy'):
        meta.append(f"`{t['claimedBy']}`")
    parts[0] += '  · ' + ' · '.join(meta)

    notes = (t.get('notes') or '').strip()
    if notes:
        for line in notes.splitlines():
            line = line.strip()
            if line:
                parts.append(f"  - {line}")

    return '\n'.join(parts)


def main():
    all_tasks = load_json(TASKS_FILE) + load_json(ARCHIVE_FILE)

    done = [t for t in all_tasks if t.get('done') or t.get('status') == 'done']
    if not done:
        # Write an empty-ish file rather than leaving a stale one
        now = datetime.now().strftime('%a %b %-d, %Y at %-I:%M %p')
        with open(DONELOG_FILE, 'w') as f:
            f.write(f"# Done Log\n_Last updated: {now}_\n\nNothing completed yet.\n")
        print("✓ DONELOG.md updated (0 tasks)", file=sys.stderr)
        return

    # Sort by timestamp descending
    done.sort(key=task_ts, reverse=True)

    # Group by week
    weeks = {}
    for t in done:
        dt = task_ts(t)
        label = week_label(dt)
        weeks.setdefault(label, []).append((t, dt))

    now = datetime.now().strftime('%a %b %-d, %Y at %-I:%M %p')
    lines = [
        "# Done Log",
        f"_Last updated: {now}_",
        f"_Tracker: http://localhost:3456_",
        "",
    ]

    for label, tasks in weeks.items():
        lines.append(f"## {label}")
        lines.append("")
        for t, dt in tasks:
            lines.append(task_line(t, dt))
        lines.append("")

    with open(DONELOG_FILE, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"✓ DONELOG.md updated ({len(done)} completed tasks)", file=sys.stderr)


if __name__ == '__main__':
    main()
