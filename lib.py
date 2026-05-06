#!/usr/bin/env python3
"""
Shared utilities for todo-tracker scripts.
Import this instead of copy-pasting slug matching logic.
"""


def slug_words(branch):
    """Extract significant words (4+ chars) from the last path segment of a branch name."""
    segment = branch.split('/')[-1]
    return [w.lower() for w in segment.split('-') if len(w) >= 4]


def slug_match_score(words, title):
    title_lower = title.lower()
    return sum(1 for w in words if w in title_lower)


def find_task_by_slug(tasks, branch):
    """
    Return the best-matching active task by branch slug.
    Requires ≥2 significant words, a score ≥2, and a clear gap of ≥2
    over the second-place task to avoid ambiguous collisions.
    Returns None if no confident, unambiguous match is found.
    """
    words = slug_words(branch)
    if len(words) < 2:
        return None

    scored = [(slug_match_score(words, t.get('title', '')), t)
              for t in tasks if not t.get('done')]
    scored.sort(key=lambda x: -x[0])

    if not scored or scored[0][0] < 2:
        return None

    second_score = scored[1][0] if len(scored) > 1 else 0
    if scored[0][0] - second_score < 2 and second_score > 0:
        return None

    return scored[0][1]


def safe_branch_filename(branch):
    """Convert a branch name to a safe filename component (replaces / with -)."""
    return branch.replace('/', '-').replace(' ', '_')


def session_task_file(branch):
    """Return the path of the temp file used to link a branch to task IDs."""
    import os, tempfile
    safe = safe_branch_filename(branch)
    return os.path.join(tempfile.gettempdir(), f'claude-task-{safe}.id')


def read_session_tasks(branch):
    """
    Return list of task IDs linked to this branch's session.
    Backward-compatible: handles both old single-ID format and new JSON-array format.
    """
    import os, json
    tf = session_task_file(branch)
    if not os.path.exists(tf):
        return []
    content = open(tf).read().strip()
    if not content:
        return []
    if content.startswith('['):
        try:
            return [tid for tid in json.loads(content) if tid]
        except Exception:
            return []
    return [content]   # legacy single-ID format


def write_session_tasks(branch, task_ids):
    """Write the list of task IDs to the session file."""
    import json
    tf = session_task_file(branch)
    with open(tf, 'w') as f:
        f.write(json.dumps(list(dict.fromkeys(task_ids))))  # deduplicate, preserve order
