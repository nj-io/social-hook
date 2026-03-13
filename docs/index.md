# Social Hook

**Automated social media content from development activity.**

Social Hook is a Claude Code hook that watches your commits, evaluates which ones are worth sharing, drafts platform-specific content, and posts it — with you in the loop at every step.

## How it works

1. **You commit code** — Social Hook's git hook fires automatically
2. **AI evaluates** — Is this commit interesting? Does it fit a narrative arc?
3. **Draft created** — Platform-specific content with optional media (code screenshots, diagrams, AI images)
4. **You review** — Approve, reject, edit, or redraft from the CLI or web dashboard
5. **It posts** — Scheduled delivery to X, LinkedIn, Telegram, or Slack

## Key features

- **Narrative arcs** — Groups related commits into coherent storylines
- **Voice memory** — Learns your style from rejections and edits
- **Multi-platform** — Tailors content per platform (thread format for X, professional for LinkedIn)
- **Media generation** — Mermaid diagrams, code screenshots (ray.so), AI images, browser captures
- **Web dashboard** — Visual pipeline monitoring and draft management
- **Full CLI** — Everything is scriptable with `--json` output

## Quick links

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md)
- [CLI Reference](cli/index.md)
- [Configuration](configuration/config.md)
- [GitHub Repository](https://github.com/nj-io/social-hook)
