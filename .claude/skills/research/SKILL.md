---
name: research
description: Research patterns and tools for the 5-stage development workflow. Use when exploring new features, debugging unfamiliar systems, or gathering best practices before implementation.
context: fork
agent: Explore
allowed-tools: Read, Grep, Glob, WebSearch, WebFetch
model: opus
---

# Research Skill

## When to Activate

- Exploring new libraries or APIs before implementation
- Investigating bug root causes in unfamiliar code
- Gathering best practices for a new feature
- Comparing implementation approaches
- Understanding unfamiliar parts of the codebase

## Research Tools

### 1. Web Search
```
WebSearch(query: "Python ChromaDB PersistentClient batch upsert pattern")
```
Use for: best practices, library comparisons, common patterns, known issues.

### 2. Library Documentation (Context7)
```
mcp__context7__resolve-library-id(libraryName: "chromadb", query: "batch insert with metadata")
mcp__context7__query-docs(libraryId: "/chroma-core/chroma", query: "PersistentClient batch upsert")
```
Use for: official API docs, version-specific patterns, correct usage.

Common libraries to look up:
- `typer` — CLI framework
- `chromadb` — vector database
- `pymupdf` / `fitz` — PDF extraction
- `pdfplumber` — PDF table extraction
- `jinja2` — template engine
- `mcp` — Model Context Protocol SDK

### 3. Codebase Exploration
```
Task(subagent_type="Explore", prompt="Find all implementations of ...")
```
Use for: understanding existing patterns, finding reusable code, tracing data flow.

### 4. Deep Analysis (Sequential Thinking)
```
mcp__sequential-thinking__sequentialthinking(thought: "...", thoughtNumber: 1, totalThoughts: 5)
```
Use for: complex architectural decisions, multi-factor tradeoff analysis, debugging hypotheses.

## Research Patterns

### Feature Research (7 steps)
1. Understand the requirement
2. Search codebase for related code
3. Read existing implementations
4. Search web for best practices
5. Check library docs via Context7
6. Compare approaches (pros/cons)
7. Write recommendation

### Bug Investigation (6 steps)
1. Reproduce the issue
2. Read error messages/logs
3. Trace the code path
4. Search for similar issues
5. Identify root cause
6. Propose fix with rationale

### Library Evaluation (6 steps)
1. Identify candidates
2. Check Context7 for official docs
3. Compare APIs and patterns
4. Check maintenance status
5. Review integration complexity
6. Recommend with tradeoffs

## Output Format

```markdown
## Research Summary: {topic}

### Problem Understanding
{What we're solving and why}

### Codebase Analysis
{Existing code, reusable patterns}

### Best Practices Found
{Key findings from research}

### Recommended Approach
{Specific recommendation with rationale}

### Sources
{Links to docs, examples, references}

### Next Steps
{Usually: proceed with /myplan}
```

## Integration with Workflow

```
/research  →  /myplan  →  /execute  →  /review  →  /wrapup
    ↑
  YOU ARE HERE
```

Research feeds directly into plan creation. Save findings in the research summary so `/myplan` can reference them.

## Quick Reference

| Tool | When to Use |
|------|-------------|
| WebSearch | Best practices, comparisons, known issues |
| Context7 | Official library documentation |
| Explore agent | Codebase patterns, dependency tracing |
| Sequential | Complex multi-factor analysis |

## Tips

1. Start broad, then narrow — don't over-constrain initial searches
2. Cross-reference web findings with official docs
3. Always check if something already exists in the codebase first
4. Document sources — future you will want to verify
5. Don't research endlessly — set a time/effort budget and synthesize
