---
description: Show what's been completed recently — this week, last week, or overall. Use when the user asks "what did I finish this week", "what have I done", "show my done tasks", "what's been completed", or "weekly summary".
---

Read the file __DONELOG_PATH__ and give a concise summary of completed work.

Focus on **this week** by default. If the user asks about a specific week or time range, filter to that.

Format:
- Group by week heading (already in the file)
- For each task: title, Jira key if present, PR link if present
- Pull out any notable notes (e.g. "Done: X" lines) as brief context
- End with a one-line count: "X tasks completed this week"

Keep it conversational and under 20 lines unless the user asks for more detail. If nothing was completed this week, say so and show last week instead.
