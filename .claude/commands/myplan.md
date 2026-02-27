# /myplan - Explore, Analyze, and Plan

Plan new features, bug fixes, or improvements. **Stage 2** of the 5-stage workflow.

## Recommended Model

```
model: opus
thinking: ultrathink
```

**Note:** Slash commands inherit the session's model. The above is the recommended configuration. Use extended thinking for deep architectural analysis.

## Usage

```
/myplan $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Description of feature, bug fix, or improvement to plan

## Workflow Position

```
1. Research → [2. PLAN] → 3. Execute → 4. Review → 5. Wrapup
                 ↑
            YOU ARE HERE
```

## Implementation

### Phase 0: Scope Declaration (CRITICAL - Do First)

**Before any exploration, declare the scope boundaries:**

```markdown
## Scope Declaration

### Change Intent
- **Type:** {feature | bugfix | refactor | style | config}
- **Single Concern:** {one-sentence description of the ONLY thing this change does}

### Concern Separation Rule
This change is ONLY about: {one thing}
This change is NOT about: {list explicitly excluded concerns}
```

**SCOPE CREEP PREVENTION RULES:**
| Current Change Type | FORBIDDEN to Also Do |
|---------------------|---------------------|
| Style/formatting | Logic changes, new features |
| Logic change | Style changes, new features, refactoring |
| Bug fix | Refactoring, new features, style improvements |
| Refactoring | New features, bug fixes (unless directly caused by refactor) |
| New feature | Unrelated refactoring, unrelated style changes |

**"While we're at it" = FORBIDDEN:**
- If you notice something unrelated that needs fixing → DO NOT fix it
- Add it to a separate TODO or note it for a future change
- Keep this change focused on ONE concern only

### Phase 1: Context Loading (REQUIRED)

**Read core documentation first:**

```
Read TECH_SPEC.md    # Technical specification and architecture
Read PLAN.md         # Implementation plan and phase breakdown
```

**Key sections to focus on:**
- TECH_SPEC.md: Architecture, module structure, interfaces
- PLAN.md: Phase breakdown, task dependencies, current progress

### Phase 2: Exploration

**Think deeply before acting.** Use the Explore agent for codebase understanding:

```
Task(
  subagent_type="Explore",
  description="Explore codebase for {feature}",
  prompt="Search for existing patterns, related code, and dependencies for: $ARGUMENTS",
  model="opus"
)
```

**Direct exploration if scope is clear:**
- Search for related files: `Glob "src/**/*.py"`
- Find relevant code: `Grep "{pattern}" --path src/`
- Read key files before planning

### Phase 3: Impact Analysis (REQUIRED)

**Analyze the impact of proposed changes before planning implementation:**

#### 3a. Direct Changes
List every file that will be modified:

| File | What Changes | Why Needed |
|------|-------------|-----------|
| `{path}` | {specific change} | {justification} |

#### 3b. Dependency Analysis
For each file to modify, trace:
- **Callers:** Functions that call this code
- **Callees:** Functions this code calls
- **Config chain:** config.toml values that affect behavior
- **Pipeline chain:** Upstream/downstream pipeline stages (ingest → chunk → embed → store → compile → serve)

#### 3c. NON-GOALS Declaration (CRITICAL)

**Explicitly list what this change will NOT touch:**

```markdown
## NON-GOALS (Do NOT Touch)

These are explicitly OUT OF SCOPE for this change:
- [ ] {file/module/feature 1} - Reason: {why excluded}
- [ ] {file/module/feature 2} - Reason: {why excluded}
- [ ] {related but separate concern} - Reason: {save for separate PR}
```

### Phase 4: Analysis

Analyze what you've found with ultrathink depth:

1. **What type of work?** (feature | bugfix | refactor | improvement | docs)
2. **Which phase?** (reference PLAN.md phases 0-5)
3. **What files affected?** (list specific files from exploration)
4. **Dependencies?** (what must exist first)
5. **Risks?** (what could go wrong)
6. **Pipeline implications?** (how does this affect the ingest → compile → serve pipeline)

### Phase 5: Test Plan (REQUIRED)

**Every plan MUST include a test specification.**

```markdown
## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | {what behavior to verify} | {test file path} | unit |
| 2 | {what behavior to verify} | {test file path} | integration |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | {user action or input} | {expected outcome} | {manual/automated} |
```

**Rules:**
- Every implementation step must have at least one corresponding test
- Tests describe BEHAVIOR, not implementation details
- Test file paths follow project conventions (`tests/test_<module>.py`)
- If a step is untestable, document WHY explicitly

### Phase 6: Plan Creation

**IMPORTANT:** Save the plan to a file named `docs/plans/PLAN_<FEATURE>.md`.

Example filenames:
- `docs/plans/PLAN_PDF_PARSER.md` - PDF parsing feature
- `docs/plans/PLAN_MCP_SERVER.md` - MCP server feature
- `docs/plans/PLAN_CHUNKING.md` - Chunking implementation

Output a structured, actionable plan:

```markdown
# Plan: $ARGUMENTS

## Scope Declaration
- **Type:** {feature | bugfix | refactor | style | config}
- **Single Concern:** {one-sentence description}
- **Phase:** {0-5 from PLAN.md}
- **Complexity:** {Low | Medium | High}
- **Risk:** {Low | Medium | High}

## Problem Statement
**What:** {concise description of what needs to be done}
**Why:** {business/technical value}
**Success:** {how we know it's done}

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `{path}` | modify/create | {specific change} |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `{function/class}` | {list} | {list} |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| {stage} | {what feeds into this} | {what this feeds} |

## NON-GOALS (Explicitly Out of Scope)
- [ ] {item 1} - Will not be touched
- [ ] {item 2} - Save for separate change

## Technical Approach

### Option A: {approach name} (Recommended)
{description of approach}
- **Pros:** {advantages}
- **Cons:** {disadvantages}

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | {task} | {file(s)} | {description} |
| 2 | {task} | {file(s)} | {description} |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | {what behavior to verify} | {test file path} | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | {user action or input} | {expected outcome} | {manual/automated} |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `{path}` | modify | {what changes} |

## Files to Create
| File | Purpose |
|------|---------|
| `{path}` | {purpose} |

## Exit Criteria
```
□ {criterion 1}
□ {criterion 2}
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: {steps}
- [ ] No unintended side effects in: {NON-GOAL areas}

## Document Updates Needed
- [ ] **TECH_SPEC.md:** {section to update, or "None"}
- [ ] **PLAN.md:** {if phase task completed, or "None"}

---

> **Last Updated:** {date}
```

### Phase 7: Save and Validate

1. **Save the plan** to `docs/plans/PLAN_<FEATURE>.md`
2. **STOP and validate with user:**

```markdown
## Validation Required

**Plan saved to:** `docs/plans/PLAN_<FEATURE>.md`

**Scope Summary:**
- Single concern: {one thing this change does}
- Files affected: {N}

**NON-GOALS confirmed:**
- {list items that will NOT be touched}

**Risk Assessment:**
- Complexity: {level}
- Side effect risk: {Low/Medium/High}

**Questions for you:**
1. Is the scope correctly bounded?
2. Are the NON-GOALS appropriate?
3. Ready to proceed with `/execute`?
```

## Plan Document Naming Convention

All plans are stored in `docs/plans/`:

| Pattern | Use For | Example |
|---------|---------|---------|
| `docs/plans/PLAN_<FEATURE>.md` | Feature plans | `PLAN_PDF_PARSER.md` |

## Best Practices Applied

- **Scope-first planning** - declare boundaries before exploration
- **Impact analysis** - understand ripple effects before coding
- **NON-GOALS declaration** - explicit exclusions prevent scope creep
- **Pipeline awareness** - understand upstream/downstream effects
- **Single concern rule** - one type of change per plan
- **Ultrathink analysis** - deep reasoning before decisions
- **Explore before planning** - understand existing code first
- **Human-in-the-loop** - validation checkpoint before execution
- **Persistent plans** - save to docs/plans/PLAN_*.md for future reference

## Next Steps

After plan approval:
```
/execute {task-description}
```

## Notes

- Always use Opus model for maximum reasoning capability
- Enable ultrathink for complex architectural decisions
- Keep plans focused - one concern per plan
- Reference specific TECH_SPEC.md sections when applicable
- Don't implement during planning - just analyze and plan
- Plan files are version-controlled and serve as project history
