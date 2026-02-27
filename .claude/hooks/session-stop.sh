#!/bin/bash
# Session stop hook for embedded-rag
# Shows pending work when Claude Code session ends (JSON protocol)

# Read stdin JSON (required even if not used)
INPUT=$(cat)

# Get project directory
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Check for active PLAN files in docs/plans/
PLAN_FILES=$(find "$PROJECT_DIR/docs/plans" -maxdepth 1 -name "PLAN_*.md" 2>/dev/null | head -5)
if [ -n "$PLAN_FILES" ]; then
    PLAN_LIST=$(echo "$PLAN_FILES" | while read -r f; do basename "$f"; done | paste -sd ", " -)
    cat <<EOF
{
  "systemMessage": "Session checkpoint — Active plans: $PLAN_LIST"
}
EOF
else
    echo '{}'
fi

exit 0
