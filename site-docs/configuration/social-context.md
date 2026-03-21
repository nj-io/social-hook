# social-context.md

Free-form markdown that defines your voice, style, audience, and content preferences. This is the primary way to personalize the content Social Hook generates.

## Location

| Priority | Location |
|----------|----------|
| 1 | `{repo}/.social-hook/social-context.md` (per-project) |
| 2 | `~/.social-hook/social-context.md` (global fallback) |

See [`examples/social-context.example.md`](https://github.com/nj-io/social-hook/blob/main/examples/social-context.example.md) for a fully commented template.

---

## Sections

The file is free-form markdown — section names are conventions, not schema. The evaluator and drafter read the entire file as context. The sections below are recommended structure.

### Author's Voice

The most important section. Describe your writing style and include 3-5 real writing samples.

```markdown
## Author's Voice

### Voice Description
Conversational, technically confident but not arrogant.
Shares the journey honestly, including challenges.
Avoids hype and marketing speak. Prefers showing over telling.

### Writing Samples

**Sample 1 (Technical explanation):**
> "The trick with context windows is knowing what to forget.
> We went with rolling window + milestone compaction."

**Sample 2 (Project update):**
> "Finally got the trigger mechanism working. PostToolUse hook
> on Bash, filter for git commits. Simple, but it took three
> failed approaches to get here."
```

### Author's Pet Peeves

Words to avoid, grammar preferences, and authenticity rules.

```markdown
## Author's Pet Peeves

### Words/Phrases to Avoid
- "Excited to announce..."
- "Game-changing"
- "Leverage" (use "use")

### Grammar/Style Preferences
- Oxford comma: Yes
- Emoji usage: Sparingly, max 1-2 per post
- Exclamation marks: Rare

### Authenticity Rules
- Never claim something works if it doesn't yet
- Show the messy parts, not just polished outcomes
```

### Writing/Narrative Strategy

Lifecycle phases, identity, and content focus. The agent infers the current phase automatically from development signals — override only if it's getting it wrong.

| Phase | Signals | Content Focus |
|-------|---------|---------------|
| research | High file churn, new directories, docs heavy | Decisions, trade-offs |
| build | Steady commits, tests growing | Progress, challenges, small wins |
| demo | Demo scripts, UX polish, README updates | Demonstrations, "it works!" |
| launch | Release tags, CHANGELOG, deploy automation | Announcements, CTAs |
| post_launch | Bugfixes, optimization | Feedback, lessons |

```markdown
## Writing/Narrative Strategy

### Identity
The author (first person, "I")

### Content Focus
- Technical deep-dives
- Progress updates
- Lessons and reflections
```

### Audience

Primary audience and platform-specific notes.

```markdown
## Audience

### Primary Audience
- **Who:** Developers, indie hackers, builders
- **Technical level:** Intermediate to advanced
- **What they care about:** Practical tools, honest experiences
- **What turns them off:** Hype, vaporware

### Platform-Specific
- **X:** Developer community. More casual.
- **LinkedIn:** Professional. More polished, focuses on learnings.
```

### Themes & Topics

What to emphasize and what to avoid.

```markdown
## Themes & Topics

### Emphasize
- AI-assisted development workflows
- Building in public
- Practical LLM usage (not hype)

### Avoid
- AI doom/safety debates
- Competitor criticism
- Unverified performance claims
```

### Visual Style

Preferences for generated media.

```markdown
## Visual Style

### Diagrams
- Clean, minimal, monochrome or limited palette

### Code Screenshots
- Dark theme, include relevant context

### Generated Images
- Modern, clean. Avoid stock photo feel.
```

### Engagement Patterns

How to handle CTAs, hashtags, and mentions.

```markdown
## Engagement Patterns

### Call-to-Action Usage
- Often: Questions to audience
- Sometimes: Follow for updates
- Never: Aggressive sales

### Hashtag Strategy
- X: Minimal (#buildinpublic only)
- LinkedIn: 3-5 relevant tags
```

---

## Additional per-project files

These files are auto-managed and loaded alongside social-context.md:

| File | Location | Description |
|------|----------|-------------|
| `memories.md` | `{repo}/.social-hook/memories.md` | Voice feedback memories from draft rejections (max 100) |
| `context-notes.md` | `{repo}/.social-hook/context-notes.md` | Expert-generated context notes (max 50) |
