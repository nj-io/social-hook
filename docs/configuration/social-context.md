# social-context.md

Voice, style, and audience guidance for content generation.

Located at `.social-hook/social-context.md` in your project directory, or `~/.social-hook/social-context.md` for global defaults.

## Example

See [`examples/social-context.example.md`](https://github.com/nj-io/social-hook/blob/main/examples/social-context.example.md) for a fully commented template.

## Sections

### Author's Voice

Describe your writing style and include 3-5 samples of your actual writing.

```markdown
## Author's Voice

### Voice Description
Conversational, technically confident but not arrogant.

### Writing Samples
> "The trick with context windows is knowing what to forget."
```

### Author's Pet Peeves

Words to avoid, grammar preferences, and authenticity rules.

```markdown
## Author's Pet Peeves

### Words/Phrases to Avoid
- "Excited to announce..."
- "Game-changing"

### Authenticity Rules
- Never claim something works if it doesn't yet
- Show the messy parts, not just polished outcomes
```

### Writing/Narrative Strategy

Lifecycle phases, identity (first person, team voice, etc.), and content focus areas.

The agent infers the current project phase (research, build, demo, launch, post-launch) from development signals. You can override with a hint if needed.

### Audience

Primary audience profile and platform-specific audience notes.

### Themes & Topics

What to emphasize and what to avoid.

### Visual Style

Preferences for diagrams, code screenshots, and generated images.

### Engagement Patterns

Call-to-action frequency, hashtag strategy, and mention policy.
