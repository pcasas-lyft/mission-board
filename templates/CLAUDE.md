# Agent Instructions

## Read this first

Check `WORKSTATUS.md` (this directory) at the start of every session to understand what's in flight, what's blocked, and where things were left off.

## Task tracker

All tasks live at **http://localhost:3456** (must be running — see below if not).

```
GET  /tasks               → all tasks
POST /tasks/new           → create a single new task (safe — appends only)
PATCH /tasks/<id>         → update a single task (preferred — never overwrites other tasks)
PATCH /tasks/<id>/log     → append a progress log entry (atomic, never loses history)
```

### At the start of every session

1. Read `WORKSTATUS.md` to find the task for this work
2. `PATCH` it to `in-progress` so the status doc stays current
3. If no matching task exists — create one first:

```bash
curl -s -X POST http://localhost:3456/tasks/new \
  -H "Content-Type: application/json" \
  -d '{"title": "What this session is doing", "status": "in-progress"}'
```

Minimal fields needed: `title` + `status`. Everything else defaults to sensible values.

### When you finish work on a task

First, append a log entry describing what you did:

```bash
curl -s -X PATCH http://localhost:3456/tasks/<id>/log \
  -H "Content-Type: application/json" \
  -d '{"text": "What you built, decided, or found out"}'
```

Then PATCH the task status:

```json
{
  "status": "in-review",
  "notes": "Next: <concrete next step>",
  "prLink": "https://github.com/...",
  "blockedOn": "",
  "claimedBy": "",
  "lastUpdated": "<ISO 8601 timestamp>"
}
```

Always set `claimedBy: ""` when finishing — this releases the lock so the task shows as available.

If you're blocked and can't continue, use `status: "blocked"` and `blockedOn: "<who/what>"` — but still clear `claimedBy`.

**Status values:** `todo` · `in-progress` · `in-review` · `blocked` · `done`

### If the tracker is unreachable

The server may not be running. Tell the user:
> The task tracker isn't running. Start it with: `python3 server.py` (from the todo-tracker directory)

Don't silently skip the status update — let the user know.

## Branch / worktree naming convention

Name branches after the task ID so the system can correlate work to tasks:

```
feat/t4-tcs-mcp
fix/t6-coverage-map-cleanup
```

Task IDs are in the `id` field of each task returned by `GET /tasks`.

## Workspace layout

```
__PARENT_DIR__/
├── CLAUDE.md          ← you are here
├── WORKSTATUS.md      ← auto-generated snapshot of all tasks
├── todo-tracker/      ← tracker server + UI
│   ├── server.py      ← python3 server.py to start
│   ├── tasks.json     ← source of truth
│   ├── gen-status.py  ← regenerates WORKSTATUS.md
│   └── index.html     ← web UI at localhost:3456
└── <repos>/           ← worktrees live here as siblings
```
