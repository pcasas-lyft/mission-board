#!/usr/bin/env python3
"""
PostToolUse hook — fires after every Bash command.

When a `git push` prints a GitHub PR URL in its output, automatically
PATCHes that URL into the current task's prLinks array.

Runs silently when no PR URL is found or no task is linked.
"""
import json, os, re, sys, subprocess, urllib.request
from datetime import datetime, timezone

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, INSTALL_DIR)
from lib import session_task_file

BASE_URL = 'http://localhost:3456'
GH_PR_RE = re.compile(r'https://github\.com/[^\s\'"]+/pull/\d+')


def pr_label(url):
    m = re.search(r'github\.com/[^/]+/([^/]+)/pull/(\d+)', url)
    return f'{m.group(1)} #{m.group(2)}' if m else url[:32]


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


def find_task_id(branch):
    """Try session file first, then claimedBy."""
    tf = session_task_file(branch)
    if os.path.exists(tf):
        tid = open(tf).read().strip()
        if tid:
            return tid
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = json.loads(r.read())
        task = next((t for t in tasks if t.get('claimedBy') == branch), None)
        if task:
            return task['id']
    except Exception:
        pass
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    # Only care about Bash commands that include a push
    cmd = (data.get('tool_input') or {}).get('command', '')
    if not re.search(r'\bgit\b.*\bpush\b', cmd):
        return

    # Extract output — Claude Code puts it in tool_response
    resp = data.get('tool_response') or {}
    if isinstance(resp, dict):
        output = resp.get('output') or resp.get('stdout') or resp.get('stderr') or ''
        if isinstance(output, list):
            output = '\n'.join(str(x) for x in output)
    elif isinstance(resp, str):
        output = resp
    else:
        output = str(resp)

    pr_urls = list(dict.fromkeys(GH_PR_RE.findall(output)))  # deduplicated, ordered
    if not pr_urls:
        return

    branch = get_branch()
    if not branch:
        return

    task_id = find_task_id(branch)
    if not task_id:
        return

    # Fetch all tasks and find the current one to merge cleanly
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            tasks = json.loads(r.read())
        task = next((t for t in tasks if t.get('id') == task_id), None)
        if not task:
            return
    except Exception:
        return

    existing = {p['url'] for p in (task.get('prLinks') or [])}
    if task.get('prLink'):
        existing.add(task['prLink'])

    new_links = list(task.get('prLinks') or [])
    added = []
    for url in pr_urls:
        if url not in existing:
            new_links.append({'url': url, 'label': pr_label(url)})
            existing.add(url)
            added.append(url)

    if not added:
        return  # All URLs already tracked

    patch = {
        'prLinks': new_links,
        'prLink': new_links[0]['url'] if new_links else '',
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
    }
    req = urllib.request.Request(
        f'{BASE_URL}/tasks/{task_id}',
        data=json.dumps(patch).encode(),
        headers={'Content-Type': 'application/json'},
        method='PATCH',
    )
    try:
        with urllib.request.urlopen(req, timeout=3):
            pass
    except Exception:
        return

    print(json.dumps({
        'systemMessage': f'🔗 Auto-linked PR{"s" if len(added) > 1 else ""} to task "{task["title"]}": {", ".join(added)}'
    }))


if __name__ == '__main__':
    main()
