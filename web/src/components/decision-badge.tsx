const decisionStyles: Record<string, string> = {
  draft: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  hold: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  skip: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  imported: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
  deferred_eval: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
};

const decisionLabels: Record<string, string> = {
  draft: "Draft",
  hold: "Hold",
  skip: "Skip",
  imported: "Imported",
  deferred_eval: "Deferred",
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
