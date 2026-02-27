# /wrapup - Finalize, Document, Commit

Finalize work, update documentation, and commit changes with proper attribution. **Stage 5** of the 5-stage workflow.

## Recommended Model

```
model: opus
thinking: ultrathink
```

**Note:** Slash commands inherit the session's model. The above is the recommended configuration. Use extended thinking for thorough documentation review.

## CRITICAL: SESSION-ONLY SCOPE

**NEVER commit, stage, restore, or modify files outside your session's changes.**

- You MUST only stage files you created or modified in THIS session
- You MUST leave all other uncommitted changes untouched
- You MUST ask the user if unsure which files belong to your session

**ABSOLUTELY FORBIDDEN:**
- `git add -A` or `git add .` (stages everything)
- `git restore .` or `git restore {file}` (discards user's work)
- `git checkout .` or `git checkout -- {file}` (discards user's work)
- `git reset --hard` (destroys all uncommitted changes)
- `git clean -f` (deletes untracked files)
- `git stash` without explicit user permission

## Usage

```
/wrapup $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Brief description for commit message (optional — will be generated if not provided)

## Workflow Position

```
1. Research → 2. Plan → 3. Execute → 4. Review → [5. WRAPUP]
                                                      ↑
                                                 YOU ARE HERE
```

## Implementation

### Phase 1: Pre-Flight Verification

**All checks must pass:**

```bash
# Lint
ruff check src/ tests/

# Type check
mypy src/hwcc/

# Tests
pytest tests/ --tb=short
```

**If any check fails, STOP and fix issues first. Do NOT commit with failures.**

### Phase 1.5: Code Cleanup

**Check for debug/test code that should be removed:**

```
Grep "print(" in src/hwcc/
Grep "breakpoint()" in src/
Grep "import pdb|import ipdb" in src/
Grep "TODO|FIXME|XXX|HACK" in src/
```

**Remove before commit:**

| Pattern | Action |
|---------|--------|
| `print("debug ...")` | Remove (keep logging.* calls) |
| `breakpoint()` | Remove |
| `import pdb` / `import ipdb` | Remove |
| Commented-out code blocks | Remove if not needed |
| Test-only imports | Remove |
| Hardcoded test values | Replace with proper values |

**Keep:**
- `logging.error()` for actual error conditions
- `logging.warning()` for unexpected but handled cases
- `logging.info()` for state changes
- `logging.debug()` for detailed tracing

### Phase 2: Review Changes

```bash
# See what will be committed
git status
git diff --stat
git diff HEAD  # Full diff
```

**Verify:**
- [ ] All changes are intentional
- [ ] No debug code left in
- [ ] No sensitive data in changes (API keys, passwords)
- [ ] Changes match the planned scope

### Phase 3: Document Updates

**Read current documents:**

```
Read TECH_SPEC.md
Read PLAN.md
```

#### Update TECH_SPEC.md if:

| Change Type | Action |
|-------------|--------|
| New file added | Add to file structure section |
| New parser | Add to parser documentation |
| API changes | Update interface documentation |
| New dependency | Update dependency list |
| Config changes | Update config documentation |

#### Update PLAN.md if:

| Change Type | Action |
|-------------|--------|
| Phase task done | Check off task |
| Decision made | Document in relevant section |
| Risk identified | Note in risks section |
| Architecture changed | Update architecture section |

**Make the updates:**

```
Edit TECH_SPEC.md  # If needed
Edit PLAN.md       # If needed
```

### Phase 4: Stage Changes

**CRITICAL: Only stage files YOU changed in this session.**

```bash
# First, check what files you actually modified:
git status

# Stage ONLY the specific files you changed
git add {specific-files-you-changed}

# Example:
git add src/hwcc/ingest/pdf.py
git add tests/test_ingest_pdf.py
git add docs/plans/PLAN_PDF_PARSER.md  # Include the plan file!
git add TECH_SPEC.md  # If you updated it
```

**DO NOT:**
- Use `git add -A` or `git add .`
- Stage files modified by the user outside this session
- Restore or discard other people's uncommitted work

**DO:**
- Stage only files you created or modified
- Include the plan file (`docs/plans/PLAN_*.md`) if one was created
- Leave other uncommitted changes in the working tree
- Ask user if unsure which files belong to this session

### Phase 5: Create Commit

**Commit format (Conventional Commits):**

```bash
git commit -m "$(cat <<'EOF'
{type}({scope}): {description}

{body - bullet points of what was done}

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

**Commit Types:**

| Type | Use When |
|------|----------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change without behavior change |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `test` | Adding/updating tests |
| `chore` | Maintenance, dependencies |
| `perf` | Performance improvement |

**Example:**

```bash
git commit -m "$(cat <<'EOF'
feat(ingest): add PDF table extraction with pdfplumber

- Implement PdfParser class with text and table extraction
- Add table-boundary-aware chunking
- Include tests for datasheet and reference manual parsing
- Update TECH_SPEC.md with parser documentation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

### Phase 6: Push to Remote

```bash
# Push to current branch
git push

# If new branch
git push -u origin {branch-name}
```

### Phase 7: Completion Summary

```markdown
## Wrapup Complete

### Commit Details
| Field | Value |
|-------|-------|
| Hash | `{short-hash}` |
| Type | {type} |
| Scope | {scope} |
| Message | {first line} |

### Statistics
- Files changed: {N}
- Insertions: +{N}
- Deletions: -{N}

### Documents Updated
| Document | Changes |
|----------|---------|
| TECH_SPEC.md | {what changed, or "No changes"} |
| PLAN.md | {what changed, or "No changes"} |

### Next Steps

{if more work in phase}
**Continue with next task:**
```
/myplan {next feature from PLAN.md}
```

{if phase complete}
**Phase {N} complete!**
- Review PLAN.md for Phase {N+1}

{if milestone reached}
**Milestone: {name}**
- Consider tagging: `git tag -a v{version} -m "{message}"`
```

## Quality Gates

**Do NOT commit if:**
- `pytest tests/` fails
- `ruff check src/ tests/` fails
- `mypy src/hwcc/` fails
- Debug code present (print, breakpoint, pdb)
- Changes don't match planned scope
- Staging files you didn't modify in this session

**OK to commit if:**
- All checks pass
- Changes match planned scope
- Documentation updated (or confirmed not needed)
- `/review` returned APPROVED (recommended)

## Learned Corrections

**If a mistake was discovered during this session**, append it to the global CLAUDE.md learned corrections section:

```
Edit ~/.claude/CLAUDE.md  # Append to "Learned Corrections" section
# Format: YYYY-MM-DD: [hwcc] Description of mistake and correct approach
```

## Rollback Procedure

If commit was wrong:

```bash
# Undo last commit (keep changes)
git reset --soft HEAD~1

# If already pushed (creates revert commit)
git revert HEAD
```

## Notes

- Always use Opus model for comprehensive wrapup
- Enable ultrathink for thorough documentation review
- Always run `/review` before wrapup for important changes
- Keep commits focused — one logical change per commit
- Push promptly to backup work
