const variantStyles: Record<string, Record<string, string>> = {
  status: {
    draft: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
    approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
    scheduled: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
    posted: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
    rejected: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
    failed: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
    cancelled: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  },
  decision: {
    draft: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
    hold: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
    skip: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
    imported: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
    deferred_eval: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  system: {
    _default: "bg-accent/10 text-accent dark:bg-accent/20",
  },
  tag: {
    _default: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
  },
  category: {
    _default: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  },
  default: {
    _default: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  },
};

const decisionLabels: Record<string, string> = {
  draft: "Draft",
  hold: "Hold",
  skip: "Skip",
  imported: "Imported",
  deferred_eval: "Deferred",
};

interface BadgeProps {
  value: string;
  variant?: "status" | "decision" | "system" | "category" | "tag" | "default";
  className?: string;
}

export function Badge({ value, variant = "default", className }: BadgeProps) {
  const styleMap = variantStyles[variant] ?? variantStyles.default;
  const style = styleMap[value] ?? styleMap._default ?? "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300";
  const label = variant === "decision" ? (decisionLabels[value] ?? value) : value;

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style} ${className ?? ""}`}>
      {label}
    </span>
  );
}
