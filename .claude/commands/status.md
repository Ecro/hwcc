# /status - Session Status

Display current session state, pending work, and workflow position. Useful for context recovery and session continuity.

## Recommended Model

```
model: opus
thinking: default
```

**Note:** Slash commands inherit the session's model. Ultrathink not needed for status checks.

## Usage

```
/status
/status $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Optional focus area: "git", "todos", "workflow", "files", or blank for full status

## Implementation

### Full Status (Default)

Run these checks and compile a status report:

#### 1. Git Status

```bash
git status --short
git log -1 --oneline
git diff --stat HEAD | tail -1
```

#### 2. Build Status

```bash
ruff check src/ tests/ 2>&1 | tail -3
mypy src/hwcc/ 2>&1 | tail -3
pytest tests/ --tb=no -q 2>&1 | tail -3
```

#### 3. Todo Status

Check the todo list state and report pending items.

#### 4. Workflow Position

Determine current workflow stage based on:
- Recent commands used
- State of git working directory
- Presence of `docs/plans/PLAN_*.md` files

### Status Report Format

```markdown
## Session Status

### Workflow Position
```
1. Research → 2. Plan → [3. EXECUTE] → 4. Review → 5. Wrapup
                              ↑
                         YOU ARE HERE
```

**Current Stage:** Execute
**Active Plan:** docs/plans/PLAN_PDF_PARSER.md

---

### Git Status

| Metric | Value |
|--------|-------|
| Branch | `{branch}` |
| Last Commit | `{hash} {message}` |
| Staged Files | {N} |
| Modified Files | {N} |
| Untracked Files | {N} |

**Changed Files:**
```
{git status --short output}
```

---

### Pending Todos

| # | Task | Status |
|---|------|--------|
| 1 | {task} | {status} |

**In Progress:** {task name or "None"}
**Remaining:** {N}

---

### Build Status

| Check | Result |
|-------|--------|
| Python Lint (ruff) | PASS / FAIL |
| Type Check (mypy) | PASS / FAIL |
| Tests (pytest) | PASS / FAIL |

---

### Recommended Next Action

Based on current state:
- {recommendation}
```

## Quick Status Modes

### Git Only

```
/status git
```

Shows only git status without build checks or todos.

### Todos Only

```
/status todos
```

Shows only pending todos without git or build status.

### Workflow Only

```
/status workflow
```

Shows current workflow position and active plan.

### Files Only

```
/status files
```

Lists recently modified files with change summary.

## Use Cases

| Scenario | Command |
|----------|---------|
| "Where was I?" | `/status` |
| "What's uncommitted?" | `/status git` |
| "What's left to do?" | `/status todos` |
| "What stage am I in?" | `/status workflow` |
| "What did I change?" | `/status files` |

## Context Recovery

If returning to a session after a break:

1. Run `/status` for full overview
2. Check active plan file if one exists
3. Review todo list for pending work
4. Continue with appropriate command

## Session Continuity Tips

After `/status`:

| Status Shows | Recommended Action |
|-------------|-------------------|
| In-progress todo | Continue that task |
| Uncommitted changes | `/review` then `/wrapup` |
| Clean state, pending todos | Pick next todo |
| All done | Start new task or close session |

## Notes

- Non-destructive (read-only)
- Lightweight and fast
- Good for session handoffs and context recovery
