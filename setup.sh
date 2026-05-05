#!/bin/bash
# setup.sh — Install or reinstall todo-tracker on this machine.
# Safe to re-run: won't overwrite tasks.json if it already exists.
#
# What it does:
#   1. Makes scripts executable
#   2. Creates tasks.json (if new install)
#   3. Generates WORKSTATUS.md
#   4. Installs ~/.claude/skills/status/SKILL.md  (/status command)
#   5. Merges hooks into ~/.claude/settings.json
#   6. Creates CLAUDE.md in the parent directory
#   7. Installs & starts launchd agent (macOS)

set -e

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$INSTALL_DIR")"
PYTHON3="$(which python3 2>/dev/null || echo python3)"
WORKSTATUS_PATH="$PARENT_DIR/WORKSTATUS.md"
USERNAME="$(whoami)"
SAFE_USERNAME="$(echo "$USERNAME" | sed 's/[^a-zA-Z0-9]/-/g')"
PLIST_LABEL="com.$SAFE_USERNAME.todo-tracker"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

# ── Pre-flight checks ────────────────────────────────────────────────────────
if ! command -v "$PYTHON3" &>/dev/null; then
  echo "❌ python3 not found. Please install Python 3 and ensure it is on your PATH."
  exit 1
fi

echo ""
echo "🔧 Setting up todo-tracker"
echo "   Install dir  : $INSTALL_DIR"
echo "   Tracker URL  : http://localhost:3456"
echo "   Status doc   : $WORKSTATUS_PATH"
echo ""

# ── 1. Make scripts executable ──────────────────────────────────────────────
chmod +x \
  "$INSTALL_DIR/on-stop.sh" \
  "$INSTALL_DIR/watch-status.sh" \
  "$INSTALL_DIR/setup.sh" \
  "$INSTALL_DIR/update.sh" 2>/dev/null || true
echo "✓ Scripts marked executable"

# ── 2. Create tasks.json (first-time only) ───────────────────────────────────
if [ ! -f "$INSTALL_DIR/tasks.json" ]; then
  echo "[]" > "$INSTALL_DIR/tasks.json"
  echo "✓ Created tasks.json"
else
  echo "✓ tasks.json already exists — kept"
fi

# ── 3. Generate WORKSTATUS.md and DONELOG.md ─────────────────────────────────
"$PYTHON3" "$INSTALL_DIR/gen-status.py"  2>/dev/null && echo "✓ Generated WORKSTATUS.md" || true
"$PYTHON3" "$INSTALL_DIR/gen-donelog.py" 2>/dev/null && echo "✓ Generated DONELOG.md"    || true

# ── 4. Install /status and /done skills ─────────────────────────────────────
DONELOG_PATH="$PARENT_DIR/DONELOG.md"

mkdir -p "$HOME/.claude/skills/status"
sed -e "s|__WORKSTATUS_PATH__|$WORKSTATUS_PATH|g" \
    "$INSTALL_DIR/templates/status-skill.md" \
    > "$HOME/.claude/skills/status/SKILL.md"
echo "✓ Installed /status skill → $HOME/.claude/skills/status/SKILL.md"

mkdir -p "$HOME/.claude/skills/done"
sed -e "s|__DONELOG_PATH__|$DONELOG_PATH|g" \
    "$INSTALL_DIR/templates/done-skill.md" \
    > "$HOME/.claude/skills/done/SKILL.md"
echo "✓ Installed /done skill   → $HOME/.claude/skills/done/SKILL.md"

# ── 5. Merge Claude Code hooks ───────────────────────────────────────────────
"$PYTHON3" "$INSTALL_DIR/install-hooks.py" "$INSTALL_DIR" "$WORKSTATUS_PATH"

# ── 6. Create CLAUDE.md in parent directory ───────────────────────────────────
if [ ! -f "$PARENT_DIR/CLAUDE.md" ]; then
  sed \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__PARENT_DIR__|$PARENT_DIR|g" \
    "$INSTALL_DIR/templates/CLAUDE.md" \
    > "$PARENT_DIR/CLAUDE.md"
  echo "✓ Created $PARENT_DIR/CLAUDE.md"
else
  # Detect stale install (unsubstituted placeholders or wrong path)
  if grep -q "__INSTALL_DIR__\|__PARENT_DIR__" "$PARENT_DIR/CLAUDE.md" 2>/dev/null; then
    echo "⚠️  $PARENT_DIR/CLAUDE.md has unsubstituted placeholders — regenerating..."
    sed \
      -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
      -e "s|__PARENT_DIR__|$PARENT_DIR|g" \
      "$INSTALL_DIR/templates/CLAUDE.md" \
      > "$PARENT_DIR/CLAUDE.md"
    echo "✓ Regenerated $PARENT_DIR/CLAUDE.md"
  else
    echo "✓ $PARENT_DIR/CLAUDE.md already exists — kept"
    echo "  (If you moved the install dir, re-run: bash setup.sh --force-claude)"
  fi
fi

# ── 7. launchd agent (macOS only) ────────────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  sed \
    -e "s|__PLIST_LABEL__|$PLIST_LABEL|g" \
    -e "s|__PYTHON3__|$PYTHON3|g" \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    "$INSTALL_DIR/templates/launchd.plist" \
    > "$PLIST_PATH"

  # Unload existing (ignore error if not loaded)
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  launchctl load "$PLIST_PATH"
  echo "✓ launchd agent installed & started ($PLIST_LABEL)"
else
  echo "ℹ  Not macOS — skipping launchd. Start the server manually:"
  echo "   python3 $INSTALL_DIR/server.py &"
fi

# ── Handle --force-claude flag ────────────────────────────────────────────────
if [[ "$1" == "--force-claude" ]]; then
  sed \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__PARENT_DIR__|$PARENT_DIR|g" \
    "$INSTALL_DIR/templates/CLAUDE.md" \
    > "$PARENT_DIR/CLAUDE.md"
  echo "✓ Regenerated $PARENT_DIR/CLAUDE.md (--force-claude)"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Setup complete!"
echo ""
echo "   Tracker UI  → http://localhost:3456"
echo "   Status doc  → $WORKSTATUS_PATH"
echo ""
echo "📌 Next steps:"
echo "   1. Restart Claude Code (or open /hooks in a session) to activate the hooks"
echo "   2. Open http://localhost:3456 to see your tracker"
echo "   3. Add tasks and start building!"
echo ""
