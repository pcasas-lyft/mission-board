#!/usr/bin/env python3
"""
Moves done tasks older than ARCHIVE_AFTER_DAYS into tasks-archive.json.
Run from on-stop.sh or manually.
"""
import json, os
from datetime import datetime, timezone, timedelta

TASKS_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.json')
ARCHIVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks-archive.json')
ARCHIVE_AFTER_DAYS = 3

def main():
    if not os.path.exists(TASKS_FILE):
        return

    with open(TASKS_FILE) as f:
        tasks = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)

    keep, archive = [], []
    for t in tasks:
        if not (t.get('done') or t.get('status') == 'done'):
            keep.append(t)
            continue

        # Use lastUpdated, fall back to createdAt, fall back to keep
        ts_str = t.get('lastUpdated') or t.get('createdAt')
        if not ts_str:
            keep.append(t)
            continue

        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            # Strip tz if naive
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            keep.append(t)
            continue

        if ts < cutoff:
            archive.append(t)
        else:
            keep.append(t)

    if not archive:
        return

    # Load existing archive and append
    existing = []
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE) as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []

    with open(ARCHIVE_FILE, 'w') as f:
        json.dump(existing + archive, f, indent=2)

    with open(TASKS_FILE, 'w') as f:
        json.dump(keep, f)

    print(f'✓ Archived {len(archive)} done task(s)', flush=True)

if __name__ == '__main__':
    main()
