# social-hook bot

Start, stop, and monitor the background bot daemon. The daemon runs the scheduler and consolidation tickers on a loop, posting approved drafts and processing holds automatically.

---

### `social-hook bot start`

Start the bot daemon.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--daemon`, `-d` | boolean | false | Run as background daemon |

---

### `social-hook bot status`

Check if the bot daemon is running.

---

### `social-hook bot stop`

Stop the bot daemon.

---
