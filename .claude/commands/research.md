# /research - Research & Best Practices

Research a feature, problem, or technology before planning. **Stage 1** of the 5-stage workflow.

## Recommended Model

```
model: opus
thinking: ultrathink
```

**Note:** Slash commands inherit the session's model. The above is the recommended configuration. Use extended thinking for thorough research.

## Usage

```
/research $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Topic, feature, problem, or technology to research

## Workflow Position

```
[1. RESEARCH] → 2. Plan → 3. Execute → 4. Review → 5. Wrapup
     ↑
   YOU ARE HERE
```

## Implementation

### Phase 1: Context Gathering

**1. Web Search for Best Practices:**

```
WebSearch("$ARGUMENTS best practices 2025 2026")
WebSearch("$ARGUMENTS Python implementation patterns")
```

**2. Deep Research (uses research agent with project context):**

```
Task(
  subagent_type="research",
  description="Research: $ARGUMENTS",
  prompt="Research best practices, patterns, and existing code for: $ARGUMENTS. Check codebase for related implementations, search web for Python patterns, and provide a structured Research Summary.",
  model="opus"
)
```

**3. Check Official Documentation (Context7):**

```
mcp__context7__resolve-library-id(libraryName: "{relevant library}")
mcp__context7__query-docs(libraryId: "{id}", query: "$ARGUMENTS")
```

### Phase 2: Analysis

Analyze findings with ultrathink depth:

1. **Problem Understanding:**
   - What exactly needs to be solved?
   - What are the constraints?
   - What are the success criteria?

2. **Approach Identification:**
   - Identify 2-3 possible approaches
   - List pros/cons for each
   - Evaluate complexity and risk

3. **Compatibility Check:**
   - How does this fit with existing architecture?
   - What dependencies are required?
   - Are there conflicts with current patterns?

### Phase 3: Research Summary

Output a structured research summary:

```markdown
## Research Summary: $ARGUMENTS

### Problem Understanding
**What:** {concise problem description}
**Constraints:** {limitations, requirements}
**Success Criteria:** {how we'll know it works}

### Best Practices Found

| Source | Key Recommendation | Relevance |
|--------|-------------------|-----------|
| {source 1} | {recommendation} | High/Medium/Low |
| {source 2} | {recommendation} | High/Medium/Low |

### Recommended Approaches

#### Option A: {name} (Recommended)
**Description:** {approach details}
**Pros:**
- {advantage 1}
- {advantage 2}
**Cons:**
- {disadvantage 1}
**Complexity:** Low/Medium/High
**Risk:** Low/Medium/High

#### Option B: {name}
**Description:** {approach details}
**Pros:** {list}
**Cons:** {list}
**Complexity:** {level}
**Risk:** {level}

### Existing Code Patterns
| File | Pattern | Relevance |
|------|---------|-----------|
| `{path}` | {pattern description} | {how it relates} |

### Dependencies Required
- {dependency 1}: {purpose}
- {dependency 2}: {purpose}

### Sources
- [{title}]({url})
- [{title}]({url})

---

## Recommendation

**Proceed with:** Option {A/B}

**Rationale:** {1-2 sentence explanation}

**Next Step:**
```
/myplan {feature based on Option A}
```
```

### Phase 4: Validation

**STOP and validate with user:**

```markdown
## Research Complete

**Topic:** $ARGUMENTS
**Approaches Found:** {N}
**Recommended:** {Option name}

**Questions for you:**
1. Does this research address your needs?
2. Should I explore any approach in more detail?
3. Ready to proceed with `/myplan`?
```

## Quick Research Mode

For faster research on familiar topics:

```
/research --quick $ARGUMENTS
```

This skips deep exploration and focuses on:
1. Quick web search
2. Codebase pattern check
3. Brief recommendation

## Integration with MCP Servers

| MCP Server | When to Use |
|------------|-------------|
| Context7 | Official library documentation |
| Sequential | Complex multi-step analysis |
| WebSearch | Current best practices, tutorials |

## Next Steps

After research approval:
```
/myplan {feature based on research findings}
```

## Notes

- Always use Opus model for comprehensive research
- Enable ultrathink for thorough analysis
- Cite sources for all recommendations
- Consider existing codebase patterns
- Research before planning, not during
