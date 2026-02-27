# /quick - Quick Fix

Fast implementation for simple, well-defined tasks. Bypasses the full 5-stage workflow for trivial changes.

## Recommended Model

```
model: opus
thinking: default
```

**Note:** Slash commands inherit the session's model. Ultrathink not needed for quick fixes. For complex tasks, use the full workflow.

## Usage

```
/quick $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Simple task description (e.g., "fix typo in README", "remove unused import in config.py")

## When to Use

| Use /quick | Use Full Workflow |
|------------|-------------------|
| Single-file changes | Multi-file coordination |
| Typo corrections | New feature implementation |
| Simple bug fixes with clear solution | Bug requiring investigation |
| Add/remove debug logging | Architectural changes |
| Small refactoring | New patterns or approaches |
| Update a constant/config | API changes |
| Fix linting issues | Security-related changes |

## Decision Guide

```
Is the change:
├── In 1 file only?
│   ├── YES → Is the solution obvious?
│   │   ├── YES → Use /quick
│   │   └── NO → Use /research or /myplan
│   └── NO → Use /myplan
└── Affecting public API?
    ├── YES → Use /myplan
    └── NO → Continue above
```

## Implementation

### Step 1: Understand the Task

Read the task and identify:
- Target file(s)
- Exact change needed
- Any dependencies

### Step 2: Read Before Write

```
Read {target-file}
```

**Never modify code you haven't read.** Even for quick fixes.

### Step 3: Test First (If Logic Change)

**If the change touches logic (not just strings/config/docs), write a failing test first:**

```bash
pytest tests/test_<module>.py -v
```

Skip this step only for: typo fixes, config changes, comment edits, style-only changes.

### Step 4: Make the Change

Implement the fix directly using Edit or Write tools.

### Step 5: Verify Build

```bash
ruff check src/ tests/ && mypy src/hwcc/
```

### Step 6: Report

```markdown
## Quick Fix Complete

**Task:** $ARGUMENTS
**File:** `{path}`
**Change:** {1-line description}

### Verification
- [x] Lint passes
- [x] Types pass

### Next Steps
- `/review --quick {file}` - If you want a quick review
- `/wrapup` - If ready to commit
- Continue working - If more changes needed
```

## Examples

### Good /quick Tasks

```bash
/quick fix typo in README.md - "recieve" should be "receive"
/quick remove unused import in cli.py
/quick update version in pyproject.toml to 0.2.0
/quick fix ruff lint error in config.py
/quick add logging to pdf parser error path
```

### Bad /quick Tasks (Use Full Workflow)

```bash
/quick implement SVD parser         # Use /research → /myplan
/quick refactor all parsers          # Use /myplan
/quick fix the bug in embedding      # Use /research first
/quick add MCP server                # Use full workflow
```

## Escalation

If during /quick you realize:
- Task is more complex than expected
- Multiple files need changes
- You need to research best practices

**STOP and escalate:**

```markdown
## Escalation

This task is more complex than expected.

**Reason:** {why it needs full workflow}

**Recommendation:** Run `/myplan {task}` instead
```

## Notes

- No ultrathink — saves time for simple tasks
- No planning phase — direct to implementation
- Still requires build verification
- Can be followed by `/wrapup` for immediate commit
