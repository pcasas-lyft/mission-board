#!/bin/bash
# Watches tasks.json and regenerates WORKSTATUS.md on every change.
# Run this in the background to keep WORKSTATUS.md always current,
# regardless of which editor or agent made the change.
#
# Usage:
#   ./watch-status.sh          # foreground
#   ./watch-status.sh &        # background

TASKS_FILE="$(dirname "$0")/tasks.json"
GEN_SCRIPT="$(dirname "$0")/gen-status.py"

echo "👁  Watching $TASKS_FILE for changes..."
python3 "$GEN_SCRIPT"  # generate once on start

fswatch -o "$TASKS_FILE" | while read _; do
  python3 "$GEN_SCRIPT"
done
