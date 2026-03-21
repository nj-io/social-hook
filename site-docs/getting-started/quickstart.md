# Quick Start

This guide gets you from zero to your first auto-generated social post in under 5 minutes.

## 1. Install

```bash
pip install social-hook
```

## 2. Quickstart

```bash
cd /path/to/your/repo
social-hook quickstart
```

This single command handles everything:

- Prompts for your Anthropic API key (or pass `--key sk-ant-...` to skip the prompt)
- Registers the current repo as a project
- Installs the git post-commit hook
- Runs AI-powered project discovery
- Generates an introductory draft based on what it learned about your project

To also evaluate recent commits:

```bash
social-hook quickstart --evaluate-last 3
```

## 3. Review your first draft

```bash
social-hook inspect pending
social-hook draft show <draft-id>
```

The quickstart generates a **preview draft** (not tied to any platform). To promote it to a real platform:

```bash
social-hook draft promote <draft-id> --platform x
```

## 4. Set your voice

Create `.social-hook/social-context.md` in your project (or `~/.social-hook/social-context.md` for global defaults). See [social-context configuration](../configuration/social-context.md) for the full template.

At minimum, describe your voice:

```markdown
## Author's Voice
Conversational, technically confident. Shares the journey honestly.
```

## 5. Configure platforms

To post to real platforms, run the setup wizard:

```bash
social-hook setup --only platforms
social-hook setup --only apikeys
```

Or configure interactively:

```bash
social-hook setup
```

## 6. Make a commit

Just commit as usual. The git hook triggers automatically:

```bash
git add .
git commit -m "feat: add WebSocket support for real-time updates"
```

Social Hook evaluates the commit. If it's post-worthy, a draft appears:

```bash
social-hook inspect pending
```

## 7. Approve and post

```bash
# See the full draft
social-hook draft show <draft-id>

# Approve it
social-hook draft approve <draft-id>

# Or approve and schedule at optimal time
social-hook draft quick-approve <draft-id>

# Or post immediately
social-hook draft post-now <draft-id>
```

## 8. Monitor

```bash
# Watch pipeline events in real time
social-hook events

# Or use the web dashboard
social-hook web
```

## What's next?

- **Fine-tune content:** Edit [content-config.yaml](../configuration/content-config.md) to adjust media tools, narrative strategy, and context limits
- **Manage narratives:** Use `social-hook arc` commands to guide storylines ([learn more](../concepts/narrative-arcs.md))
- **Import history:** Run `social-hook project import-commits` to backfill your timeline
- **Understand the pipeline:** Read [How the Pipeline Works](../concepts/pipeline.md)
- **Explore the CLI:** See the full [CLI reference](../cli/index.md)
