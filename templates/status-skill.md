---
description: Show a live status briefing of all current work — what's active, blocked, in review, and up next. Use when the user asks "what's my status", "where am I at", "what's going on", or "what should I work on".
---

Read the file __WORKSTATUS_PATH__ and give a concise status briefing:

**Right now** — what's actively being worked on (activeNow or claimedBy an agent branch)
**Blocked** — anything stuck and what it's waiting on
**In review** — waiting on someone else
**Up next** — top 2-3 things to tackle based on what's scheduled or in progress
**Done recently** — anything completed today worth noting

Keep it under 15 lines total. Conversational tone, no bullet-point walls. If something is claimed by an agent branch, mention which branch. If nothing is active, say so clearly.
