# content-config.yaml

Content guidance for LLM prompts — media tool usage, narrative strategy, and context assembly.

## Location

| Priority | Location |
|----------|----------|
| 1 | `{repo}/.social-hook/content-config.yaml` (per-project) |
| 2 | `~/.social-hook/content-config.yaml` (global fallback) |

See [`examples/content-config.example.yaml`](https://github.com/nj-io/social-hook/blob/main/examples/content-config.example.yaml) for a fully commented template.

!!! note
    This file controls *content guidance* (how the AI writes). For infrastructure settings (which platforms/models are enabled), see [config.yaml](config.md).

---

## media_tools

Per-tool content guidance for the Drafter agent. Controls *when* and *how* each tool is used. Tool *availability* is set in `config.yaml` under `media_generation.tools`.

Default tool slots: `mermaid`, `nano_banana_pro`, `playwright`, `ray_so` (always present even if omitted from YAML).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | — | Per-project override for tool availability. `null` = inherit from config.yaml |
| `use_when` | list | `[]` | Situations where this tool is appropriate |
| `constraints` | list | `[]` | Usage rules and limitations |
| `prompt_example` | string | — | Example prompt for the drafter |

```yaml
media_tools:
  mermaid:
    description: "Text-based diagram generation"
    use_when:
      - "Technical architecture explanations"
      - "Flow diagrams and processes"
    constraints:
      - "Don't overuse - can feel dry/boring"
      - "Best for technical audience"
    prompt_example: |
      Create a Mermaid diagram showing the flow from git commit
      to social post. Use graph LR orientation. Maximum 8-10 nodes.

  nano_banana_pro:
    description: "AI image generation (Google)"
    use_when:
      - "Marketing/announcement visuals"
      - "Polished graphics for launches"
    constraints:
      - "Always specify 'no text' unless text is essential"
      - "Request specific dimensions for platform"

  playwright:
    description: "Browser screenshot capture"
    use_when:
      - "Demonstrating actual UI/product"
      - "Showing working features"
    constraints:
      - "Only use when there's actual UI to show"
      - "Ensure no sensitive data visible"

  ray_so:
    description: "Code screenshot generation"
    use_when:
      - "Highlighting interesting code snippets"
      - "Code-focused posts"
    constraints:
      - "Best for short snippets (< 30 lines)"
```

### Tool selection heuristics

The drafter uses these as soft rules:

- Technical/architectural post → prefer `mermaid` (unless used in last 2 posts)
- Announcement/milestone post → prefer `nano_banana_pro`
- Working feature demo → prefer `playwright`
- Code-focused post → prefer `ray_so`
- Fallback: `nano_banana_pro`
- Variety: avoid using the same tool 3+ consecutive times

---

## strategy

Controls narrative arc management, episode variety, and posting rhythm. These are soft thresholds — the evaluator uses judgment.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `narrative_debt_threshold` | int | `3` | Force synthesis post after N reactive/opportunistic posts |
| `portfolio_window` | int | `10` | Number of recent posts to consider for variety |
| `arc_stagnation_days` | int | `14` | Flag narrative arc if no posts for N days |
| `strategy_moment_max_gap_days` | int | `7` | Force strategy review after N days of inactivity |
| `episode_preferences.favor` | list | `[]` | Episode types to prefer when applicable |
| `episode_preferences.avoid` | list | `[]` | Episode types to avoid unless necessary |

```yaml
strategy:
  narrative_debt_threshold: 3
  portfolio_window: 10
  arc_stagnation_days: 14
  strategy_moment_max_gap_days: 7
  episode_preferences:
    favor: [demo_proof, before_after]
    avoid: []
```

---

## context

Controls how much historical context is assembled into LLM prompts. Larger values = better awareness but higher token costs.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `recent_decisions` | int | `30` | Past decisions to include in prompts |
| `recent_posts` | int | `15` | Past posts to include in prompts |
| `max_tokens` | int | `150000` | Compaction threshold (triggers at ~75% of 200K window) |
| `include_readme` | bool | `true` | Include project README.md in evaluator context |
| `include_claude_md` | bool | `true` | Include CLAUDE.md in evaluator context |
| `max_doc_tokens` | int | `10000` | Max tokens allocated to project docs |
| `max_discovery_tokens` | int | `60000` | Max tokens used during project discovery |
| `max_file_size` | int | `256000` | Max file size (bytes) considered during discovery |
| `project_docs` | list | `[]` | Glob patterns for priority files to always include |
| `pending_draft_detail` | string | `"full_content"` | `"full_content"` or `"summary"` — detail level for pending drafts in evaluator prompts |
| `arc_context_chars` | int | `500` | Max chars of arc context per pending draft |
| `pending_drafts_cap` | int | `10` | Max pending drafts included in context |
| `max_hold_count` | int | `5` | Max held decisions before forcing skip |

```yaml
context:
  recent_decisions: 30
  recent_posts: 15
  max_tokens: 150000
  pending_draft_detail: full_content
  project_docs:
    - "docs/REQUIREMENTS.md"
    - "src/core/**/*.py"
```

---

## summary

Hints for when project summaries should be refreshed. The evaluator uses these as suggestions, not hard triggers.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `refresh_after_commits` | int | `20` | Suggest refresh after N commits |
| `refresh_after_days` | int | `14` | Suggest refresh after N days |

```yaml
summary:
  refresh_after_commits: 20
  refresh_after_days: 14
```
