"use client";

interface WizardStepperProps {
  steps: string[];
  currentStep: number;
  completedSteps: Set<number>;
  onStepClick: (step: number) => void;
}

export function WizardStepper({ steps, currentStep, completedSteps, onStepClick }: WizardStepperProps) {
  return (
    <>
      {/* Desktop: horizontal stepper */}
      <div className="hidden sm:flex items-center gap-1">
        {steps.map((label, i) => {
          const isActive = i === currentStep;
          const isCompleted = completedSteps.has(i);
          const isClickable = isCompleted || i <= currentStep;
          return (
            <div key={i} className="flex items-center">
              {i > 0 && (
                <div className={`mx-1 h-px w-4 ${isCompleted || i <= currentStep ? "bg-accent" : "bg-border"}`} />
              )}
              <button
                onClick={() => isClickable && onStepClick(i)}
                disabled={!isClickable}
                className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : isCompleted
                      ? "text-accent hover:bg-accent/10"
                      : "text-muted-foreground"
                } ${isClickable ? "cursor-pointer" : "cursor-default"}`}
              >
                <span
                  className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold ${
                    isActive
                      ? "bg-accent-foreground/20 text-accent-foreground"
                      : isCompleted
                        ? "bg-accent/20 text-accent"
                        : "bg-border text-muted-foreground"
                  }`}
                >
                  {isCompleted ? "\u2713" : i + 1}
                </span>
                <span className="hidden lg:inline">{label}</span>
              </button>
            </div>
          );
        })}
      </div>

      {/* Mobile: simple progress indicator */}
      <div className="flex items-center justify-between sm:hidden">
        <span className="text-sm font-medium">
          Step {currentStep + 1} of {steps.length}
        </span>
        <span className="text-sm text-muted-foreground">{steps[currentStep]}</span>
      </div>
    </>
  );
}
