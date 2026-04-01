# Narrative Arcs

Most developer social accounts post disconnected updates: "added feature X", "fixed bug Y". Narrative arcs are Social Hook's mechanism for grouping related commits into coherent storylines that build on each other.

## What arcs look like

An arc might be:

- **"Real-time dashboard"** — a 2-week thread that starts with "starting on WebSocket support", progresses through "got live updates working", and culminates in "the dashboard is live, here's a demo"
- **"Performance deep-dive"** — profiling, optimizing, benchmarking, sharing results
- **"Auth rewrite"** — the decision to rewrite, the messy middle, the before/after

Each arc produces 3-10 posts over days or weeks. The evaluator decides when a commit belongs to an arc, when to start a new one, and when an arc is complete.

## How arcs work

### Creation

Arcs are created in two ways:

1. **Evaluator-initiated** — When the evaluator sees a commit that starts a new storyline, it sets `new_arc_theme` in its response. Social Hook creates the arc automatically.
2. **Manual** — `social-hook arc create "Auth migration"` creates an arc that the evaluator can assign commits to.

Arcs are scoped to a **strategy** (via the `strategy` field on the `Arc` dataclass). A project can have multiple strategies, and each strategy has its own set of arcs. There's a hard limit of **3 active arcs per strategy** (`max_arcs_per_strategy` in config). This prevents narrative sprawl — if you're telling too many stories at once, none of them land. When the limit is hit, the evaluator must complete or abandon an existing arc before starting a new one.

### Assignment

When the evaluator returns a "draft" decision, it can set `arc_id` to assign the commit to an existing arc. The drafter then sees:

- The arc's theme
- How many posts have been made in the arc so far
- The content of up to 5 previous arc posts

This context lets the drafter write content that builds on what came before. If the evaluator assigns an arc but forgets to include reference posts, Social Hook auto-injects the arc's most recent post as a safety net.

### Continuity in drafts

When the drafter creates content for an arc post, it receives explicit instructions:

- The arc's theme and trajectory
- Previous posts in the arc (with their actual published content)
- The evaluator's angle for this specific post

This produces posts that feel like chapters, not isolated updates. A post about adding WebSocket support can reference the earlier post about the dashboard architecture.

### Completion and lifecycle

| Status | Meaning | How to get there |
|--------|---------|------------------|
| **active** | Accepting new posts | Default state after creation |
| **completed** | Story is finished | `social-hook arc complete <id>` or evaluator judgment |
| **abandoned** | Story was dropped | `social-hook arc abandon <id>` |

Completed and abandoned arcs can be resumed with `social-hook arc resume <id>`.

### Stagnation

If an active arc hasn't had a post in `arc_stagnation_days` (default 14), the evaluator receives a signal that the arc is stagnating. It might:

- Write a synthesis post to wrap up the arc
- Abandon the arc if the work has moved on
- Continue the arc if a relevant commit appears

## Narrative debt

Social Hook tracks **narrative debt** — a counter of how many reactive or opportunistic posts have been made since the last arc or synthesis post. When this exceeds `narrative_debt_threshold` (default 3), the evaluator is nudged to produce a synthesis post or advance an arc.

This prevents the account from becoming a stream of disconnected updates. After 3 one-off posts, the system pushes toward narrative cohesion.

## Strategy awareness

The evaluator also sees:

- **Portfolio window** — The last N posts (default 10) for variety analysis. It avoids repeating the same episode tags too often.
- **Episode preferences** — Your configured favored and avoided episode tags (via `EpisodePreferences` with `favor` and `avoid` lists).

Together with arcs and narrative debt, these mechanisms produce a posting pattern that feels intentional rather than automated.

## CLI commands

```bash
social-hook arc list                      # List all arcs
social-hook arc list --status active      # Filter by status
social-hook arc create "Auth migration"   # Start a new arc
social-hook arc complete <id>             # Mark as finished
social-hook arc complete <id> --notes "Shipped in v2.1"  # With notes
social-hook arc abandon <id>              # Drop a storyline
social-hook arc resume <id>              # Reactivate
```
