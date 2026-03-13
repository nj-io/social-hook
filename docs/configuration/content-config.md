# content-config.yaml

Content guidance for LLM prompts — media tool usage, narrative strategy, and context assembly.

Located at `.social-hook/content-config.yaml` in your project directory, or `~/.social-hook/content-config.yaml` for global defaults.

## Example

See [`examples/content-config.example.yaml`](https://github.com/nj-io/social-hook/blob/main/examples/content-config.example.yaml) for a fully commented template.

## Sections

### media_tools

Per-tool content guidance for the Drafter agent. Controls *when* and *how* each media tool is used (tool *availability* is set in `config.yaml`).

```yaml
media_tools:
  mermaid:
    description: "Text-based diagram generation"
    use_when:
      - "Technical architecture explanations"
    constraints:
      - "Best for technical audience"
    prompt_example: |
      Create a Mermaid diagram showing...
```

Available tools: `mermaid`, `nano_banana_pro`, `playwright`, `ray_so`

### strategy

Controls narrative arc management, episode variety, and posting rhythm.

```yaml
strategy:
  narrative_debt_threshold: 3    # Force synthesis post after N reactive posts
  portfolio_window: 10           # Recent posts to consider for variety
  arc_stagnation_days: 14        # Flag arc if no posts for N days
```

### context

Controls how much historical context is assembled into LLM prompts.

```yaml
context:
  recent_decisions: 30           # Past decisions to include
  recent_posts: 15               # Past posts to include
  max_tokens: 150000             # Compaction threshold
  pending_draft_detail: full_content  # "full_content" or "summary"
```

### summary

Hints for when project summaries should be refreshed.

```yaml
summary:
  refresh_after_commits: 20
  refresh_after_days: 14
```
