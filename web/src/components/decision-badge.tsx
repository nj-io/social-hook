const decisionStyles: Record<string, string> = {
  post_worthy: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  not_post_worthy: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  consolidate: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  deferred: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
};

const decisionLabels: Record<string, string> = {
  post_worthy: "Post Worthy",
  not_post_worthy: "Not Post Worthy",
  consolidate: "Consolidate",
  deferred: "Deferred",
};

export function DecisionBadge({ decision }: { decision: string }) {
  const style = decisionStyles[decision] ?? "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300";
  const label = decisionLabels[decision] ?? decision;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {label}
    </span>
  );
}
