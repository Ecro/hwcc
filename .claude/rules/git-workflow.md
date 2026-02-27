# Git Workflow Rules

## Commit Messages
Use Conventional Commits format:
```
{type}({scope}): {description}

{body - bullet points of what was done}

{footer}

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

### Types
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

## Staging
- Stage specific files, not `git add -A` or `git add .`
- Only stage files you modified in this session
- Leave other uncommitted changes untouched

## Safety Rules
- NEVER force push to main/master
- NEVER amend commits without explicit request
- NEVER skip hooks (--no-verify) without explicit request
- NEVER run destructive commands (reset --hard, checkout ., clean -f) without explicit request

## Branch Strategy
- Create feature branches from main
- Use descriptive branch names: `feat/feature-name`, `fix/bug-description`
- Keep commits focused — one logical change per commit

## Pre-Commit Verification
Before committing:
1. Tests pass: `pytest tests/`
2. Lint passes: `ruff check src/ tests/`
3. Format correct: `ruff format --check src/ tests/`
4. Types correct: `mypy src/hwcc/`
5. No debug code left in
6. Changes match planned scope
