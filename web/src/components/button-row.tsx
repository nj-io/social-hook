"use client";

import { sendCallback } from "@/lib/api";

interface ButtonDef {
  label: string;
  action: string;
  payload: string;
}

interface ButtonRowProps {
  buttons: ButtonDef[][];
  onEvents?: (events: unknown[]) => void;
}

export function ButtonRow({ buttons, onEvents }: ButtonRowProps) {
  if (!buttons || buttons.length === 0) return null;

  async function handleClick(action: string, payload: string) {
    try {
      const result = await sendCallback(action, payload);
      onEvents?.(result.events);
    } catch {
      // Silently handle errors - the chat will show any server responses
    }
  }

  return (
    <div className="flex flex-col gap-1">
      {buttons.map((row, ri) => (
        <div key={ri} className="flex gap-2">
          {row.map((btn, bi) => (
            <button
              key={bi}
              onClick={() => handleClick(btn.action, btn.payload)}
              className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80"
            >
              {btn.label}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
