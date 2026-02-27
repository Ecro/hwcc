#!/bin/bash
# Post-write verification reminder hook for embedded-rag
# Only reminds for Python file changes

# Read stdin JSON (required by hook protocol)
INPUT=$(cat)

# Extract file path from tool input
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

# Only show reminder for Python source files
case "$FILE_PATH" in
  *.py)
    cat << 'EOF'
{
  "continue": true,
  "systemMessage": "Python file written. Consider running: pytest tests/ -x --tb=short"
}
EOF
    ;;
  *)
    echo '{}'
    ;;
esac

exit 0
