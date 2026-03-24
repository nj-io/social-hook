interface NoteProps {
  variant?: "warning" | "info" | "success" | "error";
  className?: string;
  children: React.ReactNode;
}

const VARIANT_STYLES: Record<string, string> = {
  warning: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300",
  info: "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300",
  success: "border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300",
  error: "border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300",
};

export function Note({ variant = "warning", className = "", children }: NoteProps) {
  return (
    <div className={`rounded-md border p-3 text-sm ${VARIANT_STYLES[variant]} ${className}`}>
      {children}
    </div>
  );
}
