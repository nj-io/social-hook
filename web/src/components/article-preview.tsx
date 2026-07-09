"use client";

import { Fragment } from "react";

/**
 * Minimal article renderer for multi-media draft articles.
 *
 * Accepts either:
 *  • ``rendered_content`` — server-resolved markdown where ``![cap](media:ID)``
 *    tokens have already been rewritten to ``![cap](/api/media/...)`` paths
 *    (preferred — backend is authoritative on the token → path map).
 *  • Raw article content with unresolved tokens plus a ``specsById`` map —
 *    used as a fallback when the server hasn't resolved yet (edit preview,
 *    offline rendering). Orphan tokens survive verbatim so the
 *    ``broken_media_reference`` diagnostic can flag them upstream.
 *
 * Handles:
 *  • ``![caption](url)`` → inline ``<figure>`` with ``<img>`` and ``<figcaption>``
 *  • ``**bold**`` and ``` `code` ``` inline
 *  • Paragraph breaks on double newline, preserving single-newline line breaks
 *  • ``# heading`` through ``### heading`` (h1/h2/h3)
 *
 * Intentionally simple — no lists, no tables. Drafts that need richer markup
 * can grow this file incrementally.
 */

const IMAGE_RE = /!\[([^\]]*)\]\(([^)]+)\)/g;
const TOKEN_RE = /!\[([^\]]*)\]\(media:([a-zA-Z0-9_\-]+)\)/g;

interface ArticlePreviewProps {
  /** Either server-resolved markdown or the raw draft content. */
  content: string;
  /**
   * Optional fallback: when ``content`` still contains unresolved
   * ``media:ID`` tokens, this map is used to inline resolve them. Missing
   * ids are left verbatim so diagnostics can surface them.
   */
  specsById?: Record<string, string>;
  className?: string;
}

export function ArticlePreview({
  content,
  specsById,
  className = "",
}: ArticlePreviewProps) {
  // Fallback path: resolve any ``media:ID`` tokens against the map. Server
  // will typically have done this already (see ``rendered_content`` on the
  // advisory endpoint); this branch exists for edit-preview parity.
  const resolved = specsById
    ? content.replace(TOKEN_RE, (match, caption, mediaId) => {
        const path = specsById[mediaId];
        if (!path) return match;
        const src = path.startsWith("/") || path.startsWith("http")
          ? path
          : `/api/media/${encodeURIComponent(path)}`;
        return `![${caption}](${src})`;
      })
    : content;

  const blocks = splitBlocks(resolved);

  return (
    <article className={`space-y-4 ${className}`}>
      {blocks.map((block, i) => (
        <Fragment key={i}>{renderBlock(block)}</Fragment>
      ))}
    </article>
  );
}

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "para"; text: string };

function splitBlocks(content: string): Block[] {
  if (!content.trim()) return [];
  const paragraphs = content.split(/\n\n+/);
  const blocks: Block[] = [];
  for (const p of paragraphs) {
    const trimmed = p.trim();
    if (!trimmed) continue;
    const h3 = /^###\s+(.*)$/.exec(trimmed);
    const h2 = /^##\s+(.*)$/.exec(trimmed);
    const h1 = /^#\s+(.*)$/.exec(trimmed);
    if (h3) blocks.push({ kind: "heading", level: 3, text: h3[1] });
    else if (h2) blocks.push({ kind: "heading", level: 2, text: h2[1] });
    else if (h1) blocks.push({ kind: "heading", level: 1, text: h1[1] });
    else blocks.push({ kind: "para", text: trimmed });
  }
  return blocks;
}

function renderBlock(block: Block): React.ReactNode {
  if (block.kind === "heading") {
    const cls =
      block.level === 1
        ? "text-2xl font-semibold"
        : block.level === 2
          ? "text-xl font-semibold"
          : "text-lg font-medium";
    const Tag = (`h${block.level}`) as "h1" | "h2" | "h3";
    return <Tag className={cls}>{renderInline(block.text)}</Tag>;
  }
  // Paragraph — may contain one or more inline images, each promoted to
  // its own figure (can't nest <figure> inside <p>).
  const parts = splitByImages(block.text);
  return (
    <>
      {parts.map((part, i) =>
        part.kind === "image" ? (
          <figure key={i} className="space-y-1">
            <img
              src={part.url}
              alt={part.caption || "Article image"}
              className="max-h-96 w-full rounded-md border border-border object-contain"
            />
            {part.caption && (
              <figcaption className="text-center text-xs text-muted-foreground">
                {part.caption}
              </figcaption>
            )}
          </figure>
        ) : part.text ? (
          <p key={i} className="text-sm leading-relaxed">
            {part.text.split("\n").map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {renderInline(line)}
              </Fragment>
            ))}
          </p>
        ) : null,
      )}
    </>
  );
}

type InlinePart =
  | { kind: "image"; caption: string; url: string }
  | { kind: "text"; text: string };

function splitByImages(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  let lastIndex = 0;
  // Use a fresh RegExp each call to reset lastIndex safely.
  const re = new RegExp(IMAGE_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIndex) {
      parts.push({ kind: "text", text: text.slice(lastIndex, m.index) });
    }
    parts.push({ kind: "image", caption: m[1], url: m[2] });
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < text.length) {
    parts.push({ kind: "text", text: text.slice(lastIndex) });
  }
  return parts;
}

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={i}
          className="rounded bg-muted px-1.5 py-0.5 text-[0.85em] font-mono text-foreground"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
