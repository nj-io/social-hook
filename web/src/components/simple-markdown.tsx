"use client";

import { Fragment } from "react";

/**
 * Lightweight markdown renderer for short text blocks (summaries, descriptions).
 * Supports: paragraphs, **bold**, `inline code`, and preserves line breaks.
 * No external dependencies.
 */

function renderInline(text: string): React.ReactNode[] {
  // Match **bold** and `code` spans
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

export function SimpleMarkdown({
  content,
  className = "",
}: {
  content: string;
  className?: string;
}) {
  // Split into paragraphs on double newlines
  const paragraphs = content.split(/\n\n+/);

  return (
    <div className={`space-y-2 ${className}`}>
      {paragraphs.map((para, i) => {
        const trimmed = para.trim();
        if (!trimmed) return null;

        // Split on single newlines within a paragraph to preserve line breaks
        const lines = trimmed.split("\n");

        return (
          <p key={i} className="text-sm leading-relaxed">
            {lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {renderInline(line)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
