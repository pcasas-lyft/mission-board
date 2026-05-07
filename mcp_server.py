#!/usr/bin/env python3
"""
MCP stdio server for todo-tracker.
Exposes task management tools to Claude Code without requiring curl/bash.
"""
import json, sys, os, urllib.request, urllib.error

BASE_URL = os.environ.get("TODO_TRACKER_URL", "http://localhost:3456")


def _get(path):
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Tracker unreachable at {BASE_URL}: {e}")


def _patch(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Tracker unreachable at {BASE_URL}: {e}")


def _post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Tracker unreachable at {BASE_URL}: {e}")


# ── Tool implementations ──────────────────────────────────────────────────────

def list_tasks(args):
    tasks = _get("/tasks")
    status_filter = args.get("status")
    if status_filter:
        tasks = [t for t in tasks if t.get("status") == status_filter]
    # Return concise summary — full list can be large
    return [
        {
            "id": t.get("id"),
            "title": t.get("title"),
            "status": t.get("status"),
            "jiraKey": t.get("jiraKey", ""),
            "prLinks": t.get("prLinks", []),
            "notes": t.get("notes", ""),
            "blockedOn": t.get("blockedOn", ""),
            "lastUpdated": t.get("lastUpdated", ""),
        }
        for t in tasks
    ]


def get_task(args):
    task_id = args.get("id")
    if not task_id:
        raise ValueError("id is required")
    tasks = _get("/tasks")
    for t in tasks:
        if t.get("id") == task_id:
            return t
    raise ValueError(f"Task {task_id!r} not found")


def search_tasks(args):
    query = args.get("query", "").lower()
    if not query:
        raise ValueError("query is required")
    tasks = _get("/tasks")
    results = []
    for t in tasks:
        text = " ".join([
            t.get("title", ""),
            t.get("notes", ""),
            t.get("jiraKey", ""),
            " ".join(p.get("label", "") for p in t.get("prLinks", [])),
        ]).lower()
        if query in text:
            results.append({
                "id": t.get("id"),
                "title": t.get("title"),
                "status": t.get("status"),
                "jiraKey": t.get("jiraKey", ""),
                "prLinks": t.get("prLinks", []),
                "notes": t.get("notes", ""),
                "lastUpdated": t.get("lastUpdated", ""),
            })
    return results


def create_task(args):
    title = args.get("title")
    if not title:
        raise ValueError("title is required")
    body = {"title": title, "status": args.get("status", "todo")}
    for field in ("notes", "jiraKey", "priority", "day"):
        if field in args:
            body[field] = args[field]
    return _post("/tasks/new", body)


def update_task(args):
    task_id = args.get("id")
    if not task_id:
        raise ValueError("id is required")
    updates = {k: v for k, v in args.items() if k != "id"}
    if not updates:
        raise ValueError("No fields to update")
    return _patch(f"/tasks/{task_id}", updates)


# ── MCP protocol (JSON-RPC 2.0 over stdio) ────────────────────────────────────

TOOLS = [
    {
        "name": "list_tasks",
        "description": "List all tasks in the tracker. Optionally filter by status (todo, in-progress, in-review, blocked, done).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: todo, in-progress, in-review, blocked, done",
                    "enum": ["todo", "in-progress", "in-review", "blocked", "done"],
                }
            },
        },
    },
    {
        "name": "get_task",
        "description": "Get full details for a single task by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Task ID (e.g. '1777918541642' or 't0')"}
            },
            "required": ["id"],
        },
    },
    {
        "name": "search_tasks",
        "description": "Search tasks by keyword — matches title, notes, Jira key, and PR labels.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword or phrase"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_task",
        "description": "Create a new task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "status": {
                    "type": "string",
                    "description": "Initial status (default: todo)",
                    "enum": ["todo", "in-progress", "in-review", "blocked", "done"],
                },
                "notes": {"type": "string"},
                "jiraKey": {"type": "string", "description": "e.g. RCASE-1234"},
                "priority": {"type": "string", "enum": ["none", "low", "medium", "high"]},
                "day": {"type": "string", "description": "ISO date e.g. 2026-05-07"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_task",
        "description": "Update fields on an existing task. Only the fields you provide are changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Task ID"},
                "status": {
                    "type": "string",
                    "enum": ["todo", "in-progress", "in-review", "blocked", "done"],
                },
                "notes": {"type": "string"},
                "blockedOn": {"type": "string"},
                "claimedBy": {"type": "string"},
                "jiraKey": {"type": "string"},
                "prLinks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "label": {"type": "string"},
                        },
                        "required": ["url"],
                    },
                },
            },
            "required": ["id"],
        },
    },
]

TOOL_FNS = {
    "list_tasks": list_tasks,
    "get_task": get_task,
    "search_tasks": search_tasks,
    "create_task": create_task,
    "update_task": update_task,
}


def send(obj):
    line = json.dumps(obj)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        send({
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "todo-tracker", "version": "1.0.0"},
            },
        })

    elif method == "notifications/initialized":
        pass  # no response needed

    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})

    elif method == "tools/call":
        name = req.get("params", {}).get("name")
        args = req.get("params", {}).get("arguments", {})
        fn = TOOL_FNS.get(name)
        if not fn:
            send({"jsonrpc": "2.0", "id": req_id,
                  "error": {"code": -32601, "message": f"Unknown tool: {name}"}})
            return
        try:
            result = fn(args)
            send({"jsonrpc": "2.0", "id": req_id,
                  "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": req_id,
                  "result": {"content": [{"type": "text", "text": f"Error: {e}"}],
                             "isError": True}})
    else:
        if req_id is not None:
            send({"jsonrpc": "2.0", "id": req_id,
                  "error": {"code": -32601, "message": f"Method not found: {method}"}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(req)


if __name__ == "__main__":
    main()
