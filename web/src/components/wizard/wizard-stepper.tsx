"use client";

interface WizardStepperProps {
  steps: string[];
  currentStep: number;
  completedSteps: Set<number>;
  onStepClick: (step: number) => void;
}

export function WizardStepper({ steps, currentStep, completedSteps, onStepClick }: WizardStepperProps) {
  return (
    <div className="space-y-2">
      {/* Step badges connected by lines — full width */}
      <div className="flex w-full items-center">
        {steps.map((_, i) => {
          const isActive = i === currentStep;
          const isCompleted = completedSteps.has(i);
          const isClickable = isCompleted || i <= currentStep;
          return (
            <div key={i} className="contents">
              {i > 0 && (
                <div className={`h-px flex-1 ${isCompleted || i <= currentStep ? "bg-accent" : "bg-border"}`} />
              )}
              <button
                onClick={() => isClickable && onStepClick(i)}
                disabled={!isClickable}
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold transition-colors ${
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : isCompleted
                      ? "bg-accent/20 text-accent hover:bg-accent/30"
                      : "bg-border text-muted-foreground"
                } ${isClickable ? "cursor-pointer" : "cursor-default"}`}
                title={steps[i]}
              >
                {isCompleted ? "\u2713" : i + 1}
              </button>
            </div>
          );
        })}
      </div>

      {/* Current step label */}
      <p className="text-center text-xs text-muted-foreground">
        {steps[currentStep]}
      </p>
    </div>
  );
}
