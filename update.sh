#!/bin/bash
# update.sh — Pull the latest changes and re-apply configuration.
# Your tasks.json and tasks-archive.json are NEVER touched.
#
# Usage:
#   ./update.sh          # pull + reapply config
#   ./update.sh --skip-pull  # reapply config only (useful if you pulled manually)

set -e

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "🔄 Updating todo-tracker..."
echo ""

# ── 1. Pull latest code ───────────────────────────────────────────────────────
if [[ "$1" != "--skip-pull" ]]; then
  cd "$INSTALL_DIR"
  git pull
  echo ""
fi

# ── 2. Re-apply configuration (hooks, skill, CLAUDE.md, launchd) ──────────────
# setup.sh is idempotent — tasks.json is never overwritten
bash "$INSTALL_DIR/setup.sh"
