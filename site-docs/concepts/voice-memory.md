# Voice Memory

Social Hook generates content using your voice description in `social-context.md`, but no static document fully captures how you want to sound. Voice memory is the feedback loop — it learns from your rejections and corrections over time.

## How it works

When you reject a draft with a reason:

```bash
social-hook draft reject draft_abc123 --reason "too much jargon, my audience isn't all engineers"
```

That reason is saved as a **voice memory**:

| Date | Context | Feedback |
|------|---------|----------|
| 2026-03-13 | Rejected draft about WebSocket implementation | too much jargon, my audience isn't all engineers |

The next time the drafter generates content, it sees this memory (and up to 9 others) in its prompt, under a **Voice Memories** section. The drafter treats these as editorial guidance — hard-won knowledge about what you actually want.

## What makes good rejection reasons

The more specific your reason, the better the system learns:

| Weak | Strong |
|------|--------|
| "don't like it" | "too formal — I write casually, like I'm talking to a friend" |
| "wrong tone" | "this sounds like a press release, not a dev blog" |
| "too long" | "X free tier is 280 chars — this needs to be punchier" |
| "not relevant" | "this refactor isn't interesting to outsiders, only post user-facing changes" |

The drafter reads these verbatim. "Too much jargon" is actionable. "Bad" is not.

## Memory accumulation

Memories are stored per-project in `{repo}/.social-hook/memories.md` as a markdown table. They accumulate over time up to a maximum of 100 entries. When the limit is reached, the oldest memories are dropped.

The drafter sees the 10 most recent memories. This means your recent feedback has the strongest influence, and old preferences naturally fade unless reinforced.

## Context notes

A related but separate mechanism. When a draft is escalated to the Expert agent (via `social-hook draft redraft` or the Telegram bot's escalation flow), the expert can generate **context notes** — editorial observations that go beyond a single rejection reason.

Context notes are stored in `{repo}/.social-hook/context-notes.md` and appear alongside voice memories in both the evaluator and drafter prompts. They capture things like "this project's audience is primarily non-technical founders" or "recent posts have been too inward-looking — shift toward external impact."

## Managing memories

```bash
social-hook memory list                    # Show all memories
social-hook memory list --project <id>     # For a specific project
social-hook memory add -c "Rejected auth post" -f "don't mention security vulnerabilities in public posts"
social-hook memory delete 3                # Delete by index (1-based)
social-hook memory clear --yes             # Clear all memories
```

You can also add memories manually without rejecting a draft. This is useful for pre-loading preferences:

```bash
social-hook memory add \
  -c "Style preference" \
  -f "always use code blocks for function names, never inline backticks in tweets"
```

## How memories interact with social-context.md

`social-context.md` is your static voice description — it sets the baseline. Voice memories are dynamic corrections on top of that baseline. Think of it as:

- **social-context.md** = "Here's who I am and how I write"
- **Voice memories** = "And here's what I've learned from seeing your actual output"

If your social-context.md says "conversational tone" but you keep rejecting drafts for being too casual, the memories will steer the drafter toward a more balanced register — without you needing to rewrite the voice document.

Over time, as memories accumulate, you might notice patterns worth codifying back into `social-context.md`. That's a good practice: promote recurring feedback into the static document and clear the memory.
