# Quick Start

This guide gets you from zero to your first auto-generated social post in under 5 minutes.

## 1. Install and initialize

```bash
pip install social-hook
social-hook setup
```

Follow the wizard prompts to configure your API keys and at least one platform.

## 2. Register your project

```bash
cd /path/to/your/repo
social-hook project register
```

## 3. Set your voice

Create `.social-hook/social-context.md` in your project (or `~/.social-hook/social-context.md` for global defaults). See [social-context configuration](../configuration/social-context.md) for the full template.

At minimum, describe your voice:

```markdown
## Author's Voice
Conversational, technically confident. Shares the journey honestly.
```

## 4. Make a commit

Just commit as usual. The git hook triggers automatically:

```bash
git add .
git commit -m "feat: add WebSocket support for real-time updates"
```

Social Hook evaluates the commit. If it's post-worthy, a draft appears:

```bash
social-hook inspect pending
```

## 5. Review and approve

```bash
# See the full draft
social-hook draft show <draft-id>

# Approve it
social-hook draft approve <draft-id>

# Or approve and schedule at optimal time
social-hook draft quick-approve <draft-id>
```

## 6. Monitor

```bash
# Watch pipeline events in real time
social-hook events

# Or use the web dashboard
social-hook web
```

## What's next?

- **Fine-tune content:** Edit [content-config.yaml](../configuration/content-config.md) to adjust media tools, narrative strategy, and context limits
- **Manage narratives:** Use `social-hook arc` commands to guide storylines
- **Import history:** Run `social-hook project import-commits` to backfill your timeline
- **Explore the CLI:** See the full [CLI reference](../cli/index.md)
