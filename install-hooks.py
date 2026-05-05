#!/usr/bin/env python3
"""
Merges todo-tracker hooks into ~/.claude/settings.json.
Called by setup.sh — not meant to be run directly.

Usage: python3 install-hooks.py <install_dir> <workstatus_path>
"""
import json, os, sys

def main():
    if len(sys.argv) < 3:
        print("Usage: install-hooks.py <install_dir> <workstatus_path>", file=sys.stderr)
        sys.exit(1)

    install_dir     = sys.argv[1].rstrip('/')
    workstatus_path = sys.argv[2]
    base_url        = 'http://localhost:3456'

    # The SessionStart systemMessage (inner JSON must escape its quotes)
    session_msg = (
        'TASK TRACKER: Before starting work, check '
        + workstatus_path
        + ' to find your task. '
        + 'PATCH it to in-progress via ' + base_url + '/tasks/<id>. '
        + 'If no matching task exists, create one first with '
        + 'POST ' + base_url + '/tasks/new '
        + u'— body: {\\"title\\": \\"...\\", \\"status\\": \\"in-progress\\"}. '
        + 'Always update the task when done.'
    )

    new_hooks = {
        "SessionStart": [{"matcher": "", "hooks": [{"type": "command",
            "command": "echo '{\"systemMessage\": \"" + session_msg + "\"}'"
        }]}],
        "WorktreeRemove": [{"matcher": "", "hooks": [{"type": "command",
            "command": f"python3 {install_dir}/auto-unclaim-task.py",
            "statusMessage": "Releasing task claim..."
        }]}],
        "WorktreeCreate": [{"matcher": "", "hooks": [{"type": "command",
            "command": f"python3 {install_dir}/auto-claim-task.py",
            "statusMessage": "Linking branch to task..."
        }]}],
        "Stop": [{"matcher": "", "hooks": [{"type": "command",
            "command": f"bash {install_dir}/on-stop.sh",
            "statusMessage": "Updating task status..."
        }]}],
    }

    settings_path = os.path.expanduser("~/.claude/settings.json")
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)

    # Load existing settings (if any)
    settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except Exception:
            settings = {}

    # Merge: our hooks win for the events we manage
    existing = settings.get("hooks", {})
    existing.update(new_hooks)
    settings["hooks"] = existing

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print(f"✓ Updated {settings_path}")

if __name__ == "__main__":
    main()
