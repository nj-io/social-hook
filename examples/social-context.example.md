# Social Context: [Project Name]

> Voice, style, and audience guidance for content generation. Place a customized version as `.social-hook/social-context.md` in your project.

---

## Author's Voice

### Voice Description
Conversational, technically confident but not arrogant. Shares the journey honestly, including challenges. Avoids hype and marketing speak. Prefers showing over telling.

### Writing Samples
Include 3-5 examples of your actual writing that capture the desired voice.

**Sample 1 (Technical explanation):**
> "The trick with context windows is knowing what to forget. We went with rolling window + milestone compaction - keeps recent work sharp while preserving key decisions from earlier sessions."

**Sample 2 (Project update):**
> "Finally got the trigger mechanism working. PostToolUse hook on Bash, filter for git commits. Simple, but it took three failed approaches to get here."

**Sample 3 (Reflection):**
> "Six research documents before writing a line of code. Felt slow at first, but now every implementation decision is already made. Just executing."

---

## Author's Pet Peeves

### Words/Phrases to Avoid
- "Excited to announce..."
- "Thrilled to share..."
- "Game-changing"
- "Revolutionary"
- "Leverage" (use "use")
- "Utilize" (use "use")
- "In order to" (use "to")
- "It's important to note that..."
- "As an AI..."
- Starting with "So," or "Well,"

### Grammar/Style Preferences
- Oxford comma: Yes
- Emoji usage: Sparingly, max 1-2 per post, never in technical explanations
- Exclamation marks: Rare, only for genuine enthusiasm
- Sentence fragments: Acceptable for emphasis
- Starting sentences with "And" or "But": Allowed

### Authenticity Rules
- Never claim something works if it doesn't yet
- Acknowledge limitations and trade-offs
- Show the messy parts, not just polished outcomes
- If using AI assistance, don't hide it

---

## Writing/Narrative Strategy

### Lifecycle Phases

The project progresses through phases. The agent infers the current phase from development signals.

| Phase | Signals | Content Focus |
|-------|---------|---------------|
| research | High file churn, new directories, prototype/ paths, docs heavy | Decisions, trade-offs, approach choices |
| build | Steady commits, tests growing, architecture stabilizing | Progress, challenges, small wins |
| demo | Demo scripts, UX polish, README updates | Demonstrations, screenshots, "it works!" |
| launch | Release tags, CHANGELOG, deploy automation | Announcements, CTAs |
| post_launch | Bugfixes, optimization, iteration | Feedback, lessons, improvements |

**Current phase is inferred, not configured.** The agent observes signals and tracks confidence.

You can hint at the current phase here if the agent is getting it wrong:
- Override hint: `[none]` (let agent infer)

### Identity
Who is speaking in the content?

The author (first person, "I")

Alternatives to consider: "we" (team), project voice, avatar/character, or acknowledging AI assistance explicitly.

### Content Focus
What types of content align with this project?

- Technical deep-dives (architecture, implementation details)
- Progress updates (what's new, what's working)
- Lessons and reflections (what we learned, mistakes made)

The balance between these should be inferred based on the nature of each commit, not predetermined.

---

## Audience

### Primary Audience
- **Who:** Developers interested in AI-assisted development, indie hackers, builders
- **Technical level:** Intermediate to advanced
- **What they care about:** Practical tools, honest experiences, code they can learn from
- **What turns them off:** Hype, vaporware, "10x your productivity" claims

### Platform-Specific Audiences
Audiences may vary by platform. Note any differences here.

- **X:** Developer community, tech Twitter. More casual, tolerates hot takes.
- **LinkedIn:** Professional network. More polished, focuses on learnings and outcomes.

---

## Themes & Topics

### Emphasize
- AI-assisted development workflows
- Building in public / transparent development
- Research-first approach to projects
- Automation and developer tools
- Practical LLM usage (not hype)

### Avoid
- AI doom/safety debates (unless directly relevant)
- Competitor criticism
- Unverified performance claims
- Politics
- Anything that could age poorly

---

## Visual Style

### Diagram Style
- Clean, minimal
- Monochrome or limited color palette
- Technical but readable
- No excessive decoration

### Code Screenshots
- Dark theme preferred
- Include relevant context (filename, line numbers if helpful)
- Highlight the interesting part

### Generated Images
- Modern, clean aesthetic
- Avoid stock photo feel
- Should feel authentic to developer/tech audience

---

## Engagement Patterns

### Call-to-Action Usage
- **Often:** Questions to audience ("How do you handle X?")
- **Sometimes:** Follow for updates
- **Rarely:** Star the repo, check out the project
- **Never:** Aggressive sales, "link in bio" spam

### Hashtag Strategy
- **X:** Minimal. Only if genuinely discoverable (#buildinpublic). Never stuff.
- **LinkedIn:** Standard 3-5 relevant tags.

### Mention Strategy
- Credit tools and libraries used
- Tag people only if genuinely relevant
- Never tag for attention/engagement bait

---

## Notes

Any other context the agent should know about this project or author.

- This is a personal project, not a company
- Author has a day job - don't imply full-time dedication
- Okay to mention AI assistance in building this project
