"use client";

interface CardOption {
  id: string;
  label: string;
  description: string;
}

interface CardSelectProps {
  options: CardOption[];
  value: string;
  onChange: (id: string) => void;
  columns?: number;
}

export function CardSelect({ options, value, onChange, columns = 2 }: CardSelectProps) {
  const gridClass = columns === 3 ? "grid-cols-1 sm:grid-cols-3" : "grid-cols-1 sm:grid-cols-2";

  return (
    <div className={`grid gap-3 ${gridClass}`} role="radiogroup">
      {options.map((option) => {
        const selected = value === option.id;
        return (
          <button
            key={option.id}
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.id)}
            className={`rounded-lg border-2 p-4 text-left transition-colors ${
              selected
                ? "border-accent bg-accent/5"
                : "border-border hover:border-muted-foreground/30"
            }`}
          >
            <p className="text-sm font-medium">{option.label}</p>
            <p className="mt-1 text-xs text-muted-foreground">{option.description}</p>
          </button>
        );
      })}
    </div>
  );
}
