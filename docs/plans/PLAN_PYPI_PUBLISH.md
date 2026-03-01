# Plan: PyPI Publish — Ship hwcc v0.1.0

## Scope Declaration
- **Type:** config
- **Single Concern:** Build and publish hwcc 0.1.0 to PyPI so `pip install hwcc` works
- **Phase:** v0.1 ship checklist (final item)
- **Complexity:** Low
- **Risk:** Low (one-way publish, but TestPyPI dry-run first)

## Problem Statement
**What:** Publish hwcc to PyPI so users can `pip install hwcc`
**Why:** Last item on the v0.1 ship checklist — makes the tool installable
**Success:** `pip install hwcc && hwcc --help` works from a clean venv

## NON-GOALS (Explicitly Out of Scope)
- [ ] CI/CD pipeline — save for v1.0
- [ ] GitHub Actions publish workflow — save for v1.0
- [ ] Code changes — package is feature-complete for v0.1
- [ ] Version bumping — already at 0.1.0

## Pre-flight Checks (Already Verified)

| Check | Status |
|-------|--------|
| `pyproject.toml` metadata complete | Done — name, version, description, license, classifiers, deps, scripts |
| `README.md` exists | Done — full quickstart |
| `LICENSE` exists | Done — MIT |
| Version consistent | Done — `pyproject.toml` and `__init__.py` both say `0.1.0` |
| Hatchling build backend configured | Done — `packages = ["src/hwcc"]` |
| CLI entry point defined | Done — `hwcc = "hwcc.cli:app"` |
| PyPI name `hwcc` available | Done — 404 on pypi.org/pypi/hwcc/json |
| Jinja2 templates in package tree | Done — 7 `.j2` files in `src/hwcc/templates/` (hatchling includes by default) |

## Implementation Steps

| # | Task | Description |
|---|------|-------------|
| 1 | Install build tools | `pip install build twine` |
| 2 | Build sdist + wheel | `python -m build` |
| 3 | Verify wheel contents | `unzip -l dist/*.whl` — confirm templates included, no junk |
| 4 | Test install in clean venv | Create temp venv, install wheel, run `hwcc --help` |
| 5 | Upload to TestPyPI | `twine upload --repository testpypi dist/*` — dry run |
| 6 | Test install from TestPyPI | `pip install -i https://test.pypi.org/simple/ hwcc` |
| 7 | Upload to PyPI | `twine upload dist/*` |
| 8 | Verify from PyPI | `pip install hwcc && hwcc --help` in clean venv |
| 9 | Update PLAN.md | Mark ship checklist item done |

## Prerequisites

- PyPI account (https://pypi.org/account/register/)
- API token for PyPI (https://pypi.org/manage/account/token/)
- API token for TestPyPI (https://test.pypi.org/manage/account/token/)

## Exit Criteria
```
□ `python -m build` produces sdist + wheel without errors
□ Wheel contains all 7 Jinja2 templates
□ `hwcc --help` works from wheel install in clean venv
□ Package live on PyPI
□ `pip install hwcc && hwcc --help` works
□ PLAN.md ship checklist fully checked
```

---

> **Last Updated:** 2026-03-01
