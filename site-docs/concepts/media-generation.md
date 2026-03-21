# Media Generation

Social Hook can attach visuals to drafts — code screenshots, diagrams, AI-generated images, and browser captures. Media is generated automatically during drafting, based on the evaluator's recommendation and the drafter's spec.

## Available tools

| Tool | What it produces | Best for | Requires |
|------|-----------------|----------|----------|
| **ray_so** | Code screenshots | Highlighting clever code, short snippets | Nothing (uses ray.so service) |
| **mermaid** | Diagrams from markup | Architecture, flows, processes | Nothing (renders locally) |
| **nano_banana_pro** | AI-generated images | Announcements, polished visuals | `GEMINI_API_KEY` |
| **playwright** | Browser screenshots | Showing working UI, demos | Playwright installed (`pip install social-hook[media]`) |

## How media flows through the pipeline

### 1. Evaluator recommends

The evaluator sees the list of enabled media tools with their usage guidance (from `content-config.yaml`). Based on the commit content and episode type, it sets a `media_tool` field — or `none` if the post doesn't need a visual.

Selection heuristics (soft rules, not hard logic):

- Technical/architecture post → prefer **mermaid**
- Announcement/milestone → prefer **nano_banana_pro**
- Working feature demo → prefer **playwright**
- Code-focused post → prefer **ray_so**
- Variety: avoid the same tool 3+ consecutive times

### 2. Drafter creates the spec

The drafter receives the evaluator's tool recommendation and creates a **media spec** — a JSON object describing what to generate. Each tool has its own spec format:

**ray_so** (code screenshot):
```json
{
  "code": "def fibonacci(n):\n    a, b = 0, 1\n    ...",
  "language": "python",
  "title": "fibonacci.py"
}
```

**mermaid** (diagram):
```json
{
  "diagram": "graph LR\n  A[Commit] --> B[Evaluate]\n  B --> C[Draft]\n  C --> D[Post]"
}
```

**nano_banana_pro** (AI image):
```json
{
  "prompt": "Clean, minimal illustration of a git commit flowing through a pipeline. Developer aesthetic, no text, blue and purple palette."
}
```

**playwright** (browser screenshot):
```json
{
  "url": "http://localhost:3000/drafts",
  "selector": "#draft-panel"
}
```

### 3. Adapter generates

After the first successful draft, Social Hook dispatches the spec to the appropriate media adapter. The adapter:

1. Validates the spec
2. Generates the media (API call, rendering, or screenshot)
3. Saves output files to `~/.social-hook/media-cache/{media_id}/`
4. Returns file paths and metadata

**Media is generated once and shared across all platforms.** If you're posting to both X and LinkedIn, the same image is attached to both drafts.

### 4. Failure is non-fatal

If media generation fails (API error, timeout, invalid spec), the draft is created anyway with `last_error` set. You'll see the error in `social-hook draft show <id>`. The post will go out without media unless you fix it.

## Three-level enable check

Media tools have a three-level toggle:

| Level | Where | What it controls |
|-------|-------|-----------------|
| **Global** | `config.yaml` → `media_generation.enabled` | Master on/off for all media |
| **Per-tool** | `config.yaml` → `media_generation.tools.<name>` | Enable/disable specific tools |
| **Per-project** | `content-config.yaml` → `media_tools.<name>.enabled` | Project-level override (can only disable) |

A tool must pass all three checks to be used. The evaluator only sees tools that are fully enabled.

## Managing media after creation

```bash
social-hook draft show <id>              # See media type, spec, and file paths
social-hook draft show <id> --open       # Open media files in default viewer
social-hook draft media-regen <id>       # Re-generate from stored spec
social-hook draft media-edit <id> -s '{"code": "...", "language": "rust"}'  # Edit the spec
social-hook draft media-remove <id>      # Remove media entirely
```

### Regeneration vs editing

**Regenerate** (`media-regen`) re-runs the existing spec through the adapter. Use this when the output was bad but the spec is fine (e.g., ray.so was down).

**Edit** (`media-edit`) replaces the spec and regenerates. Use this when the spec itself needs changing (wrong code snippet, bad diagram markup, etc.).

## Customizing tool guidance

The evaluator and drafter see per-tool guidance from your `content-config.yaml`. This controls *when* and *how* each tool is used:

```yaml
media_tools:
  mermaid:
    use_when:
      - "Technical architecture explanations"
      - "Flow diagrams and processes"
    constraints:
      - "Don't overuse - can feel dry/boring"
      - "Best for technical audience"
    prompt_example: |
      Create a Mermaid diagram showing the data flow.
      Use graph LR orientation. Maximum 8-10 nodes.

  ray_so:
    use_when:
      - "Highlighting interesting code snippets"
    constraints:
      - "Best for short snippets (< 30 lines)"
      - "Include filename if relevant"
```

The `prompt_example` is particularly useful — it shapes the drafter's spec quality. A specific example produces better results than generic guidance.

## Media garbage collection

Over time, the media cache accumulates orphaned files (from deleted or superseded drafts). Clean up with:

```bash
social-hook media gc --dry-run    # See what would be removed
social-hook media gc --yes        # Remove orphaned files
```
