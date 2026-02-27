# /review - Code Review

Comprehensive code review before committing. **Stage 4** of the 5-stage workflow.

## Recommended Model

```
model: opus
thinking: ultrathink
```

**Note:** Slash commands inherit the session's model. The above is the recommended configuration. Use extended thinking for thorough code review.

## Usage

```
/review $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Optional scope: file path, module name, "recent" for recent changes, or blank for all uncommitted changes

## Workflow Position

```
1. Research → 2. Plan → 3. Execute → [4. REVIEW] → 5. Wrapup
                                          ↑
                                     YOU ARE HERE
```

## Implementation

### Phase 1: Determine Scope

```bash
# If no argument or "recent"
git diff HEAD --name-only
git status --short

# If specific file/module
# Analyze that file and its dependencies
```

### Phase 2: Load Standards

```
Read TECH_SPEC.md    # Code patterns and standards
Read PLAN.md         # Architecture decisions
```

### Phase 2.5: Load Plan & Scope

**If a plan exists for this work:**
```
Read docs/plans/PLAN_<FEATURE>.md  # Get scope boundaries
```

**Extract scope constraints:**
- Single Concern declared in plan
- Files that should be modified
- NON-GOALS (files that should NOT be touched)

### Phase 3: Invoke Code Reviewer

**Spawn the code-reviewer agent for comprehensive analysis:**

```
Task(
  subagent_type="code-reviewer",
  description="Comprehensive code review for: {scope}",
  prompt="Review all code changes for: {scope}. Changed files: {file list from git diff}. Check architecture, security, performance, Python quality, test quality. Reference TECH_SPEC.md for expected patterns.",
  model="opus"
)
```

### Phase 4: Manual Analysis Checklist

#### Scope Compliance Review
- [ ] **Single Concern maintained?** Changes align with declared intent?
- [ ] **All modified files in scope?** No unexpected files changed?
- [ ] **NON-GOALS respected?** Excluded items remain untouched?
- [ ] **No scope creep?** No "while we're at it" changes?

**Scope Creep Detection:**
| Red Flag | Description |
|----------|-------------|
| Style + Logic mixed | Formatting changes in logic PR |
| Unrelated file touched | File not in "Files to Modify" list |
| Feature + Refactor mixed | New feature includes cleanup of old code |
| NON-GOAL modified | Explicitly excluded item was changed |

#### Architecture Review
- [ ] Follows established patterns from TECH_SPEC.md?
- [ ] Module responsibilities properly separated?
- [ ] Data flow through pipeline is clear?
- [ ] Abstract interfaces used correctly?
- [ ] No unnecessary coupling between modules?

#### Python Quality
- [ ] Type hints on all public functions?
- [ ] `pathlib.Path` used (not `os.path`)?
- [ ] No bare `except:` blocks?
- [ ] Context managers for file I/O?
- [ ] `logging` module (not `print()`) for diagnostics?
- [ ] `@dataclass` for data structures?
- [ ] Abstract base classes for interfaces?
- [ ] `__all__` in `__init__.py` files?

#### Security Checklist
- [ ] No `eval()`, `exec()`, or `pickle.loads()` from untrusted sources?
- [ ] Path traversal prevention (user paths stay within project)?
- [ ] API keys only from env vars (never in config or logs)?
- [ ] Error messages don't leak filesystem paths or credentials?
- [ ] Safe document parsing (no arbitrary code execution)?

#### Performance
- [ ] ChromaDB queries efficient (metadata filtering, batching)?
- [ ] PDF parsing memory usage reasonable?
- [ ] Generators used for large iterations?
- [ ] Embedding batch sizes optimized?
- [ ] No blocking operations in async contexts?

#### Test Quality Review
- [ ] Tests exist for all new/changed behavior?
- [ ] Tests written before implementation (TDD followed)?
- [ ] Tests are independent (no order dependency)?
- [ ] Tests cover edge cases, not just happy path?
- [ ] Test names describe behavior: `test_<what>_<scenario>_<expected>`?
- [ ] External services mocked (Ollama, ChromaDB) in unit tests?
- [ ] All tests pass: `pytest tests/`?

### Phase 5: Generate Report

```markdown
## Code Review Report

### Scope
Files analyzed: {list or count}

### Scope Compliance
| Check | Status |
|-------|--------|
| Single Concern | PASS / FAIL |
| Files In Scope | PASS / FAIL |
| NON-GOALS Respected | PASS / FAIL |
| No Scope Creep | PASS / FAIL |

### Summary
| Metric | Value |
|--------|-------|
| Grade | A / B / C / D / F |
| Scope Compliance | PASS / FAIL |
| Critical Issues | {N} |
| Warnings | {N} |
| Suggestions | {N} |

---

### Critical Issues (Must Fix Before Commit)

#### [CRITICAL-1] {title}
**File:** `{path}:{line}`
**Category:** {Security | Correctness | Performance | Architecture}

**Problem:**
{description}

**Current Code:**
```python
{problematic code}
```

**Recommended Fix:**
```python
{fixed code}
```

---

### Warnings (Should Fix)

#### [WARN-1] {title}
**File:** `{path}:{line}`
**Problem:** {description}
**Suggestion:** {how to improve}

---

### Suggestions (Nice to Have)

#### [SUGGEST-1] {title}
**File:** `{path}:{line}`
**Idea:** {description}

---

### Positive Observations

- {good practice found}
- {well-implemented pattern}

---

## Verdict

**Status:** APPROVED | CHANGES_REQUESTED | NEEDS_WORK

**Summary:** {1-2 sentence assessment}

**Next Steps:**
{if APPROVED}
- Ready for `/wrapup`

{if CHANGES_REQUESTED}
- Fix critical issues listed above
- Re-run `/review` after fixes

{if NEEDS_WORK}
- Significant rework needed
- Consider revising approach with `/myplan`
```

## Quick Review Mode

For fast feedback on specific code:

```
/review --quick src/hwcc/ingest/pdf.py
```

This performs focused analysis on just that file without full agent review.

## Next Steps

After review approval:
```
/wrapup {commit description}
```

## Notes

- Always use Opus model for senior-level analysis
- Enable ultrathink for comprehensive code review
- Be thorough but constructive
- Provide code examples for fixes
- Consider project phase (MVP vs production polish)
- Reference specific TECH_SPEC.md sections when noting pattern violations
