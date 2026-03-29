"use client";

interface CardOption {
  id: string;
  label: string;
  description: string;
}

type CardSelectProps =
  | { multiSelect?: false; options: CardOption[]; value: string; onChange: (id: string) => void; columns?: number }
  | { multiSelect: true; options: CardOption[]; value: string[]; onChange: (ids: string[]) => void; columns?: number };

export function CardSelect(props: CardSelectProps) {
  const { options, columns = 2 } = props;
  const gridClass = columns === 3 ? "grid-cols-1 sm:grid-cols-3" : "grid-cols-1 sm:grid-cols-2";

  if (props.multiSelect) {
    const { value, onChange } = props;
    return (
      <div className={`grid gap-3 ${gridClass}`} role="group">
        {options.map((option) => {
          const selected = value.includes(option.id);
          return (
            <button
              key={option.id}
              role="checkbox"
              aria-checked={selected}
              onClick={() => {
                const next = selected ? value.filter((id) => id !== option.id) : [...value, option.id];
                onChange(next);
              }}
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

  // Single-select (radio) — existing behavior
  const { value, onChange } = props;
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
