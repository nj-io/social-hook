# How the Pipeline Works

Every time you commit code, Social Hook decides whether it's worth sharing, writes platform-specific content, and queues it for posting. This guide explains what happens at each stage — what the AI sees, how it decides, and where you can intervene.

## The big picture

```
git commit
    │
    ▼
┌─────────┐     ┌───────────┐     ┌─────────┐     ┌──────────┐     ┌──────────┐
│ Trigger  │────▶│ Evaluator │────▶│ Drafter  │────▶│ Schedule  │────▶│  Review  │
│ (hook)   │     │ (LLM)     │     │ (LLM)    │     │ (algo)    │     │  (you)   │
└─────────┘     └───────────┘     └─────────┘     └──────────┘     └──────────┘
                     │                                                    │
                     ▼                                                    ▼
               skip / hold                                             Post
```

A commit flows left to right. At the evaluator, most commits are filtered out (skipped). The ones that make it through are drafted, scheduled, and presented for your review before anything is posted.

---

## Stage 1: Trigger

**What fires it:** A git post-commit hook calls `social-hook trigger --commit <hash> --repo <path>`.

**What happens:**

1. **Project lookup** — Matches the repo path to a registered project. If not found, tries matching by git remote origin (handles worktrees pointing to the same repo). If still not found, exits silently — the hook fires for every repo, not just registered ones.

2. **Guard checks** — Is the project paused? Is there a branch filter, and are we on the right branch? If either fails, the commit is ignored.

3. **Commit parsing** — Extracts the full commit message, author date, stat summary (files changed, insertions, deletions), and the complete diff. For merge commits or initial commits, uses appropriate git commands to get a meaningful diff.

4. **Rate limiting** — If too many evaluations have fired recently, the commit is deferred for later processing rather than hammering the LLM API.

The trigger is designed to be fast and non-blocking. It runs in the post-commit hook, so if anything fails (network down, API error), it exits gracefully without disrupting your git workflow.

---

## Stage 2: Context Assembly

Before the evaluator LLM sees anything, Social Hook assembles a comprehensive context window. This is the single most important part of the system — the quality of the evaluation depends entirely on what context the LLM receives.

### What goes into the prompt

The evaluator's system prompt is assembled from these sections, in order:

| Section | What it contains | Why it matters |
|---------|-----------------|----------------|
| **Base instructions** | Decision criteria, episode types, tool schemas | Tells the LLM what it can do |
| **Social context** | Your voice, persona, audience (from `social-context.md`) | Grounds decisions in your brand |
| **Current state** | Lifecycle phase, narrative debt, audience introduction status | Awareness of where things stand |
| **Active arcs** | Up to 3 narrative arcs with their recent posts | Enables storyline continuity |
| **Pending drafts** | Drafts awaiting review (up to 10) | Prevents duplicate topics |
| **Held commits** | Previously deferred commits (up to 20) | Can be absorbed into new decisions |
| **Platform config** | Which platforms, priority, content filters | Knows what it's writing for |
| **Scheduling state** | Posts today, slots remaining, weekly limit | Makes capacity-aware decisions |
| **Voice memories** | Last 10 rejection reasons from your feedback | Learns from your corrections |
| **Context notes** | Expert-generated notes from escalations | Accumulated editorial wisdom |
| **Development narrative** | Session narratives from journey capture (up to 5) | Understands the development story, not just the diff |
| **Recent history** | Last 30 decisions + last 15 posts | Pattern and variety awareness |
| **Project summary** | 500-800 token project description | Big-picture understanding |
| **README / CLAUDE.md** | Project docs (if enabled) | Technical understanding |
| **Media tools** | Available tools with usage guidance | Knows what visuals are possible |
| **Strategy preferences** | Favored/avoided episode types, portfolio window | Respects your editorial preferences |
| **The commit** | Hash, message, file list, and full diff | The actual thing being evaluated |

The full diff is truncated to roughly 37,500 tokens (1/4 of the context budget) to leave room for everything else. If the total prompt exceeds the configured `max_tokens` (default 150,000), older history is progressively removed.

### First-run discovery

On the very first commit for a project (no summary exists yet), Social Hook runs a **two-pass discovery**:

1. **File listing** — Lists all project files and asks the LLM to select the 5-15 most important ones
2. **Summary generation** — Loads those files (within a token budget) and asks the LLM to produce a 500-800 token project summary

This summary is cached and refreshed periodically (configurable via `summary.refresh_after_commits` and `summary.refresh_after_days`).

---

## Stage 3: Evaluation

The evaluator LLM receives the assembled prompt and must respond via a structured tool call (`log_evaluation`). It cannot respond with free text — the output is always structured.

### Decisions

The evaluator returns one of three actions:

| Action | Meaning | What happens next |
|--------|---------|-------------------|
| **draft** | This commit is worth sharing | Proceeds to drafting |
| **skip** | Not interesting enough | Recorded and forgotten |
| **hold** | Interesting, but wait for more context | Queued for later; may be absorbed by a future commit |

Each decision includes structured metadata:

- **reason** — Why this action was chosen (logged, visible in `social-hook inspect log`)
- **angle** — The specific angle for the post (if drafting)
- **episode_type** — Classification: `milestone`, `demo_proof`, `before_after`, `synthesis`, `launch`, `postmortem`, `incremental`, `decision`, `opportunistic`
- **post_category** — `standalone`, `arc` (part of a narrative), or `reactive`
- **arc_id** / **new_arc_theme** — Narrative arc assignment or creation
- **media_tool** — Which media tool the drafter should use (or `none`)
- **consolidate_with** — IDs of held commits to absorb into this decision
- **reference_posts** — Past posts the drafter should build on

### Hold mechanics

Held commits accumulate up to `max_hold_count` (default 5). When the limit is reached, the oldest held commit is forced to "skip" — this prevents unbounded accumulation. The evaluator sees all held commits and can choose to absorb them into a future "draft" decision using `consolidate_with`.

### Queue actions

The evaluator can also act on existing pending drafts:

- **supersede** — Replace a stale draft with the new one
- **merge** — Combine the new commit's content into an existing draft
- **drop** — Discard a draft that's no longer relevant

This gives the evaluator editorial control over the draft queue, not just the current commit.

---

## Stage 4: Drafting

If the evaluator chose "draft", the system creates platform-specific content for each enabled platform.

### Per-platform loop

For each enabled platform that passes the content filter:

1. **Content filter** — Each platform has a filter (`all`, `notable`, or `significant`) that determines which episode types are allowed. A `decision` episode on a `significant`-only platform is filtered out. This is how you tune posting volume per platform.

2. **LLM call** — The drafter receives a prompt with your voice context, the evaluator's angle and reasoning, the commit diff (truncated to 8,000 chars — less than the evaluator, since the drafter needs less technical detail), and platform-specific instructions:
   - **X free tier**: 280 character limit, avoid links in main post
   - **X paid tier**: 25,000 char limit, option of single post or thread
   - **LinkedIn**: Professional tone
   - **Custom platforms**: Uses your configured description, format, and max_length

3. **Thread detection** — For X, if the content overflows the character limit or the drafter indicates multiple beats, the system makes a second LLM call specifically for thread formatting (numbered tweets, each within limits).

4. **Media generation** — Happens once (shared across platforms) after the first successful draft. If the evaluator recommended a media tool, the system generates it:
   - Validates the tool is enabled (global → per-tool → project-level override)
   - Dispatches to the appropriate adapter (ray.so, Mermaid, Gemini, Playwright)
   - Saves output to `~/.social-hook/media-cache/`
   - If media generation fails, the draft is created anyway — media errors are non-fatal

### Preview mode

If no platforms are configured, the system auto-injects a synthetic "preview" platform (2,000 char limit, filter=all). This lets you run the full pipeline and see what it would generate without setting up real platform credentials.

### Audience introduction

The first-ever draft for a project gets special treatment:

- The drafter receives a bold instruction that this is the first post and must be introductory
- Project documentation (from discovery or README) is always included
- The draft is marked `is_intro=True`
- A guard prevents creating duplicate intro drafts

After the first draft is created, the project is marked `audience_introduced=True` and subsequent drafts are normal.

---

## Stage 5: Scheduling

Each draft gets a suggested posting time calculated by an algorithm (not the LLM).

### How optimal time is calculated

1. **Weekly limit check** — If you've hit `max_per_week` (default 10), the draft is **deferred** (no time assigned, requires manual action later)

2. **7-day search** — Scans the next 7 days looking for the first available slot that satisfies all constraints:
   - On an optimal day (default: Tue, Wed, Thu)
   - At an optimal hour (default: 9, 12, 17 in your timezone)
   - Under the daily post limit for this platform
   - Respecting the minimum gap from the last post (default: 30 minutes)
   - Not conflicting with already-scheduled drafts

3. **Fallback** — If no optimal slot exists in 7 days, schedules for 1 hour from now

Per-platform scheduling overrides take precedence over global defaults. So X might allow 3 posts/day with 30-minute gaps while LinkedIn allows 1 post/day with 48-hour gaps.

### Deferred drafts

When a draft is deferred (weekly limit hit), it gets status "deferred" with no suggested time. The evaluator is aware of deferred drafts and factors them into future decisions. You can manually approve deferred drafts from the CLI or dashboard.

---

## Stage 6: Notification

After a draft is created (or a decision is made), notifications go out to all enabled channels:

| Channel | How it works |
|---------|-------------|
| **Web** | Written to the SQLite DB as events; the dashboard picks them up via WebSocket |
| **Telegram** | Sent to all allowed chat IDs with inline review buttons (Quick Approve, Schedule, Edit, Reject) |
| **Slack** | Similar to Telegram, sent to configured channels |

If the Telegram bot daemon isn't running, buttons are stripped from messages (since there's no callback handler to process them).

For skip/hold decisions, a simpler notification is sent (if `notification_level` is set to `all_decisions`; the default). Set it to `drafts_only` to suppress these.

---

## Stage 7: Review

This is where you come in. Every draft waits for your action before posting.

### From the CLI

```bash
social-hook inspect pending          # See what's waiting
social-hook draft show <id>          # Full draft with media
social-hook draft approve <id>       # Approve for posting
social-hook draft quick-approve <id> # Approve + schedule optimal time
social-hook draft reject <id> -r "too technical"  # Reject with feedback
social-hook draft edit <id> -c "..."              # Edit content
social-hook draft redraft <id> -a "focus on UX"   # AI redraft with new angle
social-hook draft schedule <id> -t 2026-03-15T09:00  # Manual schedule
```

### From the web dashboard

The dashboard at `social-hook web` provides the same actions with a visual interface, plus real-time pipeline event toasts.

### From Telegram/Slack

If the bot daemon is running, you can approve, reject, and schedule drafts directly from the chat interface using inline buttons or conversational commands.

### Voice memory

When you reject a draft with a reason (`--reason "too technical for this audience"`), the rejection reason is saved as a **voice memory**. These memories are injected into future drafter prompts, so the system progressively learns your preferences. Memories accumulate up to 100 per project and can be managed with `social-hook memory list/add/delete/clear`.

---

## Stage 8: Posting

The scheduler tick (`social-hook scheduler-tick`) runs periodically and posts all approved drafts whose scheduled time has arrived.

For each due draft:
1. Calls the platform adapter (X API, LinkedIn API, etc.)
2. Records the result (success with external URL, or failure with error)
3. Emits events for the dashboard

Failed posts can be retried with `social-hook draft retry <id>`.

---

## Consolidation

A separate tick (`social-hook consolidation-tick`) handles batch processing:

### Held decision processing

Held commits accumulate when the evaluator defers decisions. The consolidation tick processes them in two modes:

- **notify_only** (default) — Sends a summary notification listing the held batch. No re-evaluation occurs. This is a reminder to check what's been deferred.
- **re_evaluate** — Combines all held commits into a synthetic batch and runs them through the full evaluation pipeline as a group. The evaluator sees the combined context and can produce a synthesis draft.

### Draft overflow alerting

If more than 3 drafts (configurable) accumulate within a 4-hour window for any platform, a notification alert is sent suggesting manual review. This catches situations where the evaluator is being too aggressive.

---

## Debugging

### Watch events in real time

```bash
social-hook events              # Live stream
social-hook events --json       # Machine-readable
social-hook events --entity decision  # Filter to decisions only
```

### Inspect the decision log

```bash
social-hook inspect log              # Last 20 decisions
social-hook inspect log --limit 50   # More history
social-hook inspect log --json       # For scripting
```

### Test without side effects

```bash
social-hook test --repo . --last 5   # Evaluate last 5 commits (no DB writes)
social-hook --dry-run trigger --commit abc123 --repo .  # Full pipeline, no writes
```

### Check scheduling state

```bash
social-hook inspect pending          # Pending drafts
social-hook inspect platforms        # Platform config
social-hook inspect usage            # Token usage and costs
```
