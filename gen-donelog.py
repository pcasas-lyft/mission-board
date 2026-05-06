#!/usr/bin/env python3
"""
Reads completed tasks from tasks.json + tasks-archive.json
and writes DONELOG.md, grouped by week (most recent first).

Run directly or via on-stop.sh.
"""
import json, os, sys
from datetime import datetime, timezone, timedelta

INSTALL_DIR   = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE    = os.path.join(INSTALL_DIR, 'tasks.json')
ARCHIVE_FILE  = os.path.join(INSTALL_DIR, 'tasks-archive.json')
JIRA_CFG_FILE = os.path.join(INSTALL_DIR, 'jira-config.json')
DONELOG_FILE  = os.path.normpath(os.path.join(INSTALL_DIR, '..', 'DONELOG.md'))

def load_jira_base():
    if not os.path.exists(JIRA_CFG_FILE):
        return ''
    try:
        with open(JIRA_CFG_FILE) as f:
            return json.load(f).get('baseUrl', '')
    except Exception:
        return ''


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
    return f"Week of {monday.strftime('%a %b')} {monday.day}, {monday.year}"


def fmt_date(dt):
    return f"{dt.strftime('%b')} {dt.day}"


def fmt_log_date(iso):
    try:
        d = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return f"{d.strftime('%b')} {d.day}"
    except Exception:
        return ''

def fmt_now():
    """Cross-platform 'Mon May 5, 2026 at 3:04 PM' — avoids %-d/%-I (macOS-only)."""
    n = datetime.now()
    h = n.hour % 12 or 12
    return f"{n.strftime('%a %b')} {n.day}, {n.year} at {h}:{n.strftime('%M')} {n.strftime('%p')}"

def task_line(t, dt, jira_base=''):
    # Header line
    header = f"~~**{t['title']}**~~"
    meta = [f"Completed {fmt_date(dt)}"]
    if t.get('jiraKey'):
        if jira_base:
            meta.append(f"[{t['jiraKey']}]({jira_base}/browse/{t['jiraKey']})")
        else:
            meta.append(f"`{t['jiraKey']}`")
    if t.get('specLink'):
        meta.append(f"[📋 Spec]({t['specLink']})")
    if t.get('prLink'):
        meta.append(f"[PR]({t['prLink']})")
    header += '  · ' + ' · '.join(meta)

    parts = [f"- {header}"]

    # Notes / next steps (if any — useful context on why it was done)
    notes = (t.get('notes') or '').strip()
    if notes:
        first_line = notes.splitlines()[0].strip()
        if first_line:
            parts.append(f"  - 📌 {first_line}")

    # Full log, most recent first
    log = t.get('log') or []
    for entry in reversed(log):
        date_str = fmt_log_date(entry.get('date', ''))
        prefix = f"**{date_str}:** " if date_str else ''
        parts.append(f"  - {prefix}{entry['text'].strip()}")

    return '\n'.join(parts)


def main():
    jira_base = load_jira_base()
    all_tasks = load_json(TASKS_FILE) + load_json(ARCHIVE_FILE)

    # Deduplicate by id (a task may appear in both files during a partial archive run)
    _seen_ids: set = set()
    _deduped = []
    for t in all_tasks:
        tid = t.get('id')
        if tid and tid in _seen_ids:
            continue
        _seen_ids.add(tid)
        _deduped.append(t)
    all_tasks = _deduped

    done = [t for t in all_tasks if t.get('done') or t.get('status') == 'done']
    if not done:
        # Write an empty-ish file rather than leaving a stale one
        now = fmt_now()
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

    now = fmt_now()
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
            lines.append(task_line(t, dt, jira_base=jira_base))
        lines.append("")

    with open(DONELOG_FILE, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"✓ DONELOG.md updated ({len(done)} completed tasks)", file=sys.stderr)


if __name__ == '__main__':
    main()
