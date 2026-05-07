#!/usr/bin/env python3
"""
PostToolUse hook — fires after WebFetch.

When an agent fetches a URL that looks like a project document
(Google Doc, Confluence, Figma, Notion, Quip), automatically adds
it to the current task's `docs` array so future sessions can find
it without searching.

Only fires for known doc-hosting domains — random reference URLs
(MDN, Stack Overflow, GitHub, etc.) are ignored.
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, INSTALL_DIR)
from lib import read_session_tasks

BASE_URL = 'http://localhost:3456'

# (url-pattern, type-key, display-label)
DOC_PATTERNS = [
    (r'docs\.google\.com/document/',     'gdoc',       'Google Doc'),
    (r'docs\.google\.com/spreadsheets/', 'gsheet',     'Google Sheet'),
    (r'docs\.google\.com/presentation/', 'gslides',    'Google Slides'),
    (r'figma\.com/(design|file)/',       'figma',      'Figma'),
    (r'\.atlassian\.net/wiki/',          'confluence', 'Confluence'),
    (r'\.atlassian\.net/jira/',          'jira',       'Jira'),
    (r'notion\.so/',                     'notion',     'Notion'),
    (r'quip\.com/',                      'quip',       'Quip'),
]

IGNORE_PATTERNS = [
    r'localhost',
    r'github\.com',
    r'stackoverflow\.com',
    r'developer\.android\.com',
    r'kotlinlang\.org',
    r'developer\.apple\.com',
    r'mdn\.mozilla\.org',
]


def classify_url(url):
    """Return (type_key, display_label) if url is a doc, else None."""
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, url, re.I):
            return None
    for pattern, type_key, label in DOC_PATTERNS:
        if re.search(pattern, url, re.I):
            return type_key, label
    return None


def extract_title(url, response_content):
    """Best-effort title from URL path or response content."""
    # Try first H1 heading from markdown/text response
    if response_content:
        m = re.search(r'^#\s+(.+)$', str(response_content), re.MULTILINE)
        if m:
            title = m.group(1).strip()
            if len(title) < 120:
                return title

    # Figma: https://figma.com/design/<id>/Title-Words -> "Title Words"
    m = re.search(r'figma\.com/(?:design|file)/[^/]+/([^/?#]+)', url)
    if m:
        return re.sub(r'[-_]', ' ', m.group(1)).strip()

    # Confluence: .../pages/12345/Page+Title -> "Page Title"
    m = re.search(r'/pages/\d+/([^/?#]+)', url)
    if m:
        return urllib.request.unquote_plus(m.group(1)).replace('+', ' ').strip()

    # Notion: notion.so/My-Page-abc123 -> "My Page"
    m = re.search(r'notion\.so/([^/?#]+)', url)
    if m:
        slug = re.sub(r'-[a-f0-9]{20,}$', '', m.group(1))
        return re.sub(r'[-_]', ' ', slug).strip()

    # Last resort: hostname
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return url[:60]


def get_branch():
    import subprocess
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


def find_task_ids(branch):
    """Return all task IDs linked to this session (supports multi-task sessions)."""
    return read_session_tasks(branch)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    # Only care about WebFetch
    if data.get('tool_name') != 'WebFetch':
        return

    url = (data.get('tool_input') or {}).get('url', '').strip()
    if not url:
        return

    classification = classify_url(url)
    if not classification:
        return

    type_key, type_label = classification

    branch = get_branch()
    if not branch:
        return

    task_ids = find_task_ids(branch)
    if not task_ids:
        return

    # Use the first (most recently started) task in the session
    task_id = task_ids[-1]

    # Fetch all tasks and find this one
    try:
        with urllib.request.urlopen(f'{BASE_URL}/tasks', timeout=3) as r:
            all_tasks = json.loads(r.read())
        task = next((t for t in all_tasks if t.get('id') == task_id), None)
        if not task:
            return
    except Exception:
        return

    # Deduplicate — don't add if URL already in docs
    existing_docs = task.get('docs') or []
    if any(d.get('url') == url for d in existing_docs):
        return

    # Extract title from response
    resp = data.get('tool_response') or {}
    content = resp.get('content') or resp.get('text') or ''
    title = extract_title(url, content)

    new_doc = {
        'url': url,
        'title': title,
        'type': type_key,
        'addedAt': datetime.now(timezone.utc).isoformat(),
    }

    patch = {
        'docs': existing_docs + [new_doc],
        'lastUpdated': new_doc['addedAt'],
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
        'systemMessage': f'📎 Auto-linked {type_label} to task "{task["title"]}": {title}'
    }))


if __name__ == '__main__':
    main()
