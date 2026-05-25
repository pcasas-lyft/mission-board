# Mission Board — Agent Setup Guide

This is a personal task tracker built for Claude Code agents. Read this before doing anything.

## What this repo is

A single-file web UI + Python server that runs locally at `http://localhost:3456`. Tasks live in `tasks.json` (gitignored — it stays on the machine). `WORKSTATUS.md` is auto-generated from tasks and lives one directory up (`../WORKSTATUS.md`).

## First time on a new machine

### 1. Prerequisites
```bash
brew install terminal-notifier   # Mac notifications (optional but recommended)
brew install fswatch             # live reload for Cursor (optional)
python3 --version                # needs Python 3.8+
```

### 2. Clone and run setup
```bash
cd ~/src   # or wherever you keep repos — must match the path in ../CLAUDE.md
git clone git@github.com:pcasas-lyft/mission-board.git todo-tracker
cd todo-tracker
bash setup.sh
```

`setup.sh` will:
- Start the server via launchd (auto-restarts on crash, starts on login)
- Install Claude Code hooks into `~/.claude/settings.json`
- Create `../CLAUDE.md` (the agent workspace instructions one level up)
- Create the launchd plist at `~/Library/LaunchAgents/com.<username>.todo-tracker.plist`

### 3. Restart Claude Code
Run `/hooks` in a session or restart the app to activate the hooks.

### 4. Restore task data (switching machines)

Tasks are **not in git** — they live in `tasks.json`. To migrate from the old machine:

**Option A — Snapshot archive (recommended)**

On the old machine, create a snapshot:
```bash
tar -czf ~/Desktop/mission-board-snapshot-$(date +%Y%m%d).tar.gz \
  -C ~/src/todo-tracker \
  tasks.json tasks-archive.json backups/
```

Transfer the `.tar.gz` to the new machine (AirDrop, USB, etc.), then:
```bash
tar -xzf ~/Desktop/mission-board-snapshot-*.tar.gz -C ~/src/todo-tracker/
```

Then restart the server:
```bash
launchctl unload ~/Library/LaunchAgents/com.$(whoami).todo-tracker.plist
launchctl load   ~/Library/LaunchAgents/com.$(whoami).todo-tracker.plist
```

**Option B — Restore from in-app backup**

If backups exist at `todo-tracker/backups/`, open http://localhost:3456,
click the 🗄 button in the header, and pick a snapshot to restore.

Or via curl:
```bash
# Restore latest backup
curl -s -X POST http://localhost:3456/tasks/restore

# Restore a specific backup
curl -s -X POST "http://localhost:3456/tasks/restore?file=tasks.20260525T134200.json"
```

### 5. Re-add Jira config (not in snapshots for security)
Go to http://localhost:3456 → click **Jira** → paste your Personal Access Token.

---

## Day-to-day: what agents need to know

### Task tracker API
```
GET  /tasks              → all tasks (JSON array)
POST /tasks/new          → append one task {"title": "...", "status": "todo"}
PATCH /tasks/<id>        → merge-update a single task (safe, never overwrites other tasks)
PATCH /tasks/<id>/log    → append a timestamped log entry
DELETE /tasks/<id>       → delete a task
GET  /backups            → list available backup snapshots
POST /tasks/restore      → restore from latest (or ?file=<name>) backup
```

**Always use PATCH, never POST /tasks** — the full-replace endpoint has a destruction guard
(rejects if new list would delete >50% of tasks) but PATCH is the safe default.

### Task structure
```json
{
  "id": "abc123",
  "title": "What needs doing",
  "status": "todo | in-progress | in-review | blocked | done",
  "day": "2026-05-25 | unscheduled",
  "priority": "high | medium | low | none",
  "ongoing": false,
  "parentId": "",
  "notes": "Done: X\nNext: Y",
  "subtasks": [{"id": "st1", "text": "subtask text", "done": false}],
  "prLinks": [{"url": "https://github.com/...", "label": "repo #123"}],
  "jiraKey": "RCASE-1234",
  "specLink": "filename.md or https://...",
  "blockedOn": "",
  "log": [{"date": "2026-05-25T10:00:00Z", "text": "What happened"}],
  "done": false,
  "lastUpdated": "2026-05-25T10:00:00Z",
  "createdAt": "2026-05-20T09:00:00Z"
}
```

### Project hierarchy
- **Project**: `ongoing: true`, no `parentId` — appears in the Active Projects band
- **Task**: has `parentId` pointing to a project — appears in day columns / backlog
- **Subtask**: lightweight `{id, text, done, day}` entry inside a task's `subtasks[]` array

### At the start of every session
1. Read `../WORKSTATUS.md` to see what's in flight
2. PATCH the relevant task to `in-progress`
3. If no matching task exists, create one with `POST /tasks/new`

### When finishing work
```bash
curl -s -X PATCH http://localhost:3456/tasks/<id> \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in-review",
    "notes": "Done: <what you did>\nNext: <next step>",
    "prLinks": [{"url": "https://github.com/...", "label": "repo #N"}],
    "lastUpdated": "<ISO timestamp>"
  }'
```

### MCP tools (preferred over curl)
The `todo-tracker` MCP server exposes: `list_tasks`, `get_task`, `search_tasks`,
`create_task`, `update_task`, `log_entry`. Use these instead of raw curl when available.

---

## Troubleshooting

**Server not running:**
```bash
curl -s http://localhost:3456/tasks | head -c 50   # should return JSON

# Start manually
python3 ~/src/todo-tracker/server.py

# Or reload launchd
launchctl unload ~/Library/LaunchAgents/com.$(whoami).todo-tracker.plist
launchctl load   ~/Library/LaunchAgents/com.$(whoami).todo-tracker.plist
```

**Hooks not firing:** Run `/hooks` in a Claude Code session or restart the app.

**Moved the repo:** Re-run `bash setup.sh` — it re-applies all path-dependent config.

**Tasks disappeared:** Click 🗄 in the UI header to restore from a backup. Backups are
created automatically before every write and kept at `todo-tracker/backups/`.
