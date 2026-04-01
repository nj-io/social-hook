/**
 * Text that clamps to a few lines when collapsed, wraps fully when expanded.
 * Used in table cells where column width is constrained but full content
 * should be visible on row expansion.
 */
export function ExpandableText({
  text,
  expanded,
  placeholder = "-",
  collapsedLines = 3,
}: {
  text: string | null | undefined;
  expanded: boolean;
  placeholder?: string;
  collapsedLines?: number;
}) {
  if (!text) return <span>{placeholder}</span>;
  return (
    <p
      className={expanded ? "whitespace-pre-wrap break-words" : "break-words"}
      style={expanded ? undefined : {
        display: "-webkit-box",
        WebkitLineClamp: collapsedLines,
        WebkitBoxOrient: "vertical",
        overflow: "hidden",
      }}
    >
      {text}
    </p>
  );
}
