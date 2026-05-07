#!/usr/bin/env python3
"""
Merges todo-tracker hooks and MCP server config into ~/.claude/settings.json.
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

    new_hooks = {
        "SessionStart": [{"matcher": "", "hooks": [{"type": "command",
            "command": f"python3 {install_dir}/session-start.py",
            "statusMessage": "Loading work status...",
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
        except Exception as e:
            print(f"⚠️  Could not parse {settings_path} ({e}) — starting fresh.", file=sys.stderr)
            settings = {}

    # Merge: our hooks win for the events we manage
    existing = settings.get("hooks", {})
    existing.update(new_hooks)
    settings["hooks"] = existing

    # Register MCP server — idempotent (overwrites our own entry only)
    mcp_servers = settings.get("mcpServers", {})
    mcp_servers["todo-tracker"] = {
        "command": "python3",
        "args": [f"{install_dir}/mcp_server.py"],
    }
    settings["mcpServers"] = mcp_servers

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print(f"✓ Updated {settings_path} (hooks + MCP server)")

if __name__ == "__main__":
    main()
