# /execute - Implement with Verification

Execute implementation based on a plan, with continuous verification and scope enforcement. **Stage 3** of the 5-stage workflow.

## Recommended Model

```
model: opus
thinking: ultrathink
```

**Note:** Slash commands inherit the session's model. The above is the recommended configuration. Use extended thinking for careful implementation.

## Usage

```
/execute $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Task description or phase reference (e.g., "Phase 0", "add PDF parser", "fix config loading")

## Workflow Position

```
1. Research → 2. Plan → [3. EXECUTE] → 4. Review → 5. Wrapup
                             ↑
                        YOU ARE HERE
```

## Implementation

### Phase 0: Scope Validation (CRITICAL - Do First)

**Load and validate the plan:**

```
Read docs/plans/PLAN_<FEATURE>.md  # Load the specific plan for this task
```

**Extract and confirm scope boundaries:**

```markdown
## Scope Confirmation

### From Plan:
- **Single Concern:** {extracted from plan}
- **Change Type:** {feature | bugfix | refactor | style | config}

### Files In Scope:
{list from plan's "Files to Modify" and "Files to Create"}

### NON-GOALS (Do NOT Touch):
{list from plan's NON-GOALS section}
```

**STOP if no plan exists.** Run `/myplan` first to establish scope.

### Phase 1: Context & Plan Loading

**Load context documents:**

```
Read TECH_SPEC.md    # Get exact code patterns to follow
Read PLAN.md         # Find phase/task details, architecture
```

**Identify from plan:**
- Phase number and tasks
- Exit criteria (verification requirements)
- Dependencies on previous work

### Phase 2: Pre-Implementation Checklist

Before writing code, verify:

- [ ] Plan exists (from `/myplan` or clear user requirements)
- [ ] Scope boundaries are clear (Single Concern + NON-GOALS)
- [ ] All dependencies are met
- [ ] Tests currently pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types pass: `mypy src/hwcc/`
- [ ] Working directory is clean or changes are intentional

### Phase 3: TDD Implementation Loop (RED-GREEN-REFACTOR)

**For each task in the plan, follow the TDD loop. Tests come FIRST.**

#### 3a. Scope Check (Before Each Edit)

```
□ Is this file in the plan's "Files to Modify" or "Files to Create"?
□ Does this change align with the "Single Concern"?
□ Is this file NOT in the NON-GOALS list?
```

**If any answer is NO:**
```markdown
SCOPE VIOLATION DETECTED

Attempted: {what you were about to do}
Reason: {why it violates scope}

Options:
1. Skip this change (recommended for NON-GOAL items)
2. Ask user if scope should be expanded
3. Note for separate PR: TODO(separate-pr): {description}
```

#### 3b. RED - Write Failing Test First

**Before writing ANY implementation code, write the test:**

1. Read the plan's Test Plan section for this task
2. Create/update the test file with the test case
3. Run the test and **verify it FAILS**:

```bash
pytest tests/test_<module>.py -v
```

4. If the test PASSES before implementation, the test is wrong — it's not testing new behavior. Fix the test.

**ENFORCEMENT RULE:** Do NOT write implementation code until you have a failing test for the behavior you're about to implement.

#### 3c. Read Before Write (CRITICAL)

```
Read {file-to-modify}  # ALWAYS read first
```

**Never modify code you haven't read.** Understand existing patterns before changing.

#### 3d. GREEN - Minimal Implementation

Write **only enough code** to make the failing test pass:
- Follow code patterns from TECH_SPEC.md exactly
- Match existing style and conventions
- Use proper type hints (no `Any`)
- Use `pathlib.Path` (not `os.path`)
- Include error handling with specific exceptions
- Use context managers for file I/O
- Use `logging` module (not `print()`)
- **Stay within declared scope**

Run the test again and **verify it PASSES**:

```bash
pytest tests/test_<module>.py -v
```

#### 3e. REFACTOR (If Needed)

With tests green, improve code quality:
- Extract duplicated logic
- Improve naming
- Simplify complex expressions

Run **ALL tests** after refactoring to ensure nothing broke:

```bash
pytest tests/ && ruff check src/ tests/
```

If any test breaks during refactor, revert the refactor change.

#### 3f. REPEAT

Go back to **3b (RED)** for the next test case / task in the plan.

#### 3g. Track Progress

Use TaskCreate / TaskUpdate to track progress:

- "RED: Write test for {task 1}" — mark `completed` when test written
- "GREEN: Implement {task 1}" — mark `in_progress` while coding
- "Verify build" — mark `pending` until Phase 4

#### 3h. Verify After Each Major Change

```bash
ruff check src/ tests/ && mypy src/hwcc/
```

#### TDD Exceptions

TDD is **not required** for:
- Pure configuration file changes
- Documentation updates
- Simple constant/string changes
- Template files (.j2)

For these, proceed directly with implementation and verification.

### Phase 4: Build Verification

**Full verification:**

```bash
# Lint check
ruff check src/ tests/

# Format check
ruff format --check src/ tests/

# Type check
mypy src/hwcc/

# All tests
pytest tests/ -v
```

### Phase 5: Final Test Suite

**Run ALL tests to confirm nothing is broken:**

```bash
pytest tests/ -v --tb=short
```

**All tests should already pass from TDD loop in Phase 3.** This is a final confirmation.

### Phase 6: Exit Criteria & Scope Check

**Verify against plan's exit criteria:**

```markdown
## Exit Criteria Verification

From docs/plans/PLAN_<FEATURE>.md:

- [ ] {criterion 1 from plan}
- [ ] {criterion 2 from plan}
- [ ] No ruff violations
- [ ] No mypy errors
- [ ] All pytest tests pass
```

**Verify scope was respected:**

```markdown
## Scope Compliance Check

- [ ] All changes are within "Files to Modify" list
- [ ] No NON-GOAL items were touched
- [ ] Single Concern was maintained (no scope creep)
```

### Phase 7: Implementation Summary

```markdown
## Execution Complete

### Summary
**Task:** $ARGUMENTS
**Status:** Complete | Partial | Blocked
**Scope Compliance:** Yes | No (explain)

### Scope Declaration (from plan)
- **Single Concern:** {what this change does}
- **NON-GOALS respected:** Yes | No

### Changes Made
| File | Type | Description | In Scope? |
|------|------|-------------|-----------|
| `{path}` | {added/modified} | {description} | Yes |

### Build Status
- [x] `ruff check` - PASS
- [x] `mypy` - PASS
- [x] `pytest` - PASS

### Verification
- [x] Exit criteria verified
- [x] Scope compliance verified

### Out-of-Scope Items Noticed (for future PRs)
| Item | Why Not Fixed Now |
|------|-------------------|
| {item} | NON-GOAL / different concern |

### Next Steps
- `/review` - Code review before committing
- `/wrapup` - Commit if confident in changes
```

## Multi-Agent Orchestration (Advanced)

For complex tasks, use specialized agents:

```
# For code implementation subtask
Task(
  subagent_type="general-purpose",
  description="Implement {specific feature}",
  prompt="Implement {detailed requirements}. SCOPE: Only modify {files}. NON-GOALS: {list}",
  model="opus"
)

# For exploration during implementation
Task(
  subagent_type="Explore",
  description="Find {pattern/file}",
  prompt="Search for {what you need}",
  model="opus"
)
```

## Error Recovery

If tests fail:
1. Read the error message carefully
2. Check recent changes with `git diff`
3. Fix incrementally, verify after each fix
4. If stuck, use `/review` to analyze the issue

## Notes

- Always use Opus model for maximum implementation quality
- Enable ultrathink for complex code changes
- Follow TECH_SPEC.md code patterns exactly
- Don't modify docs during execution — track updates for `/wrapup`
- Commit only after `/review` or when confident
