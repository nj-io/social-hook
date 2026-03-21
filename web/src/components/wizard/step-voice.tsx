"use client";

import { useState } from "react";

interface StepVoiceProps {
  voiceTone: string;
  writingSamples: string[];
  petPeeves: string[];
  grammarPrefs: Record<string, boolean>;
  onVoiceToneChange: (v: string) => void;
  onWritingSamplesChange: (v: string[]) => void;
  onPetPeevesChange: (v: string[]) => void;
  onGrammarPrefsChange: (v: Record<string, boolean>) => void;
  templatePreFilled: boolean;
}

const TONE_PRESETS = [
  "Conversational and direct",
  "Professional and clear",
  "Technical and detailed",
  "Casual and playful",
  "Authoritative and confident",
];

const GRAMMAR_OPTIONS = [
  "Oxford comma",
  "Sentence case headings",
  "No exclamation marks",
  "American English",
  "British English",
];

export function StepVoice({
  voiceTone,
  writingSamples,
  petPeeves,
  grammarPrefs,
  onVoiceToneChange,
  onWritingSamplesChange,
  onPetPeevesChange,
  onGrammarPrefsChange,
  templatePreFilled,
}: StepVoiceProps) {
  const [newSample, setNewSample] = useState("");
  const [newPeeve, setNewPeeve] = useState("");
  const [expanded, setExpanded] = useState(!templatePreFilled);

  if (templatePreFilled && !expanded) {
    return (
      <div className="animate-wizard-dissolve space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Voice & Style</h3>
          <p className="mt-1 text-sm text-muted-foreground">Pre-filled from your strategy template.</p>
        </div>
        <div className="rounded-md border border-border bg-muted/50 p-4 text-sm">
          <p><strong>Tone:</strong> {voiceTone}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setExpanded(true)}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Customize
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Voice & Style</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Define the tone and style for your content.
        </p>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Tone</label>
        <textarea
          value={voiceTone}
          onChange={(e) => onVoiceToneChange(e.target.value)}
          placeholder="Describe your desired writing tone..."
          rows={2}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
        />
        <div className="mt-2 flex flex-wrap gap-1">
          {TONE_PRESETS.map((preset) => (
            <button
              key={preset}
              onClick={() => onVoiceToneChange(preset)}
              className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-accent hover:text-accent"
            >
              {preset}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Writing samples</label>
        <div className="space-y-1">
          {writingSamples.map((sample, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="flex-1 truncate rounded-md border border-border px-3 py-1.5 text-xs">{sample}</span>
              <button
                onClick={() => onWritingSamplesChange(writingSamples.filter((_, j) => j !== i))}
                className="text-xs text-destructive hover:underline"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={newSample}
            onChange={(e) => setNewSample(e.target.value)}
            placeholder="Paste a tweet, post, or sentence that sounds like you..."
            className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            onKeyDown={(e) => {
              if (e.key === "Enter" && newSample.trim()) {
                onWritingSamplesChange([...writingSamples, newSample.trim()]);
                setNewSample("");
              }
            }}
          />
          <button
            onClick={() => {
              if (newSample.trim()) {
                onWritingSamplesChange([...writingSamples, newSample.trim()]);
                setNewSample("");
              }
            }}
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
          >
            Add
          </button>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Pet peeves</label>
        <div className="flex flex-wrap gap-1">
          {petPeeves.map((peeve, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-xs"
            >
              {peeve}
              <button
                onClick={() => onPetPeevesChange(petPeeves.filter((_, j) => j !== i))}
                className="text-muted-foreground hover:text-destructive"
              >
                x
              </button>
            </span>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={newPeeve}
            onChange={(e) => setNewPeeve(e.target.value)}
            placeholder="Things to avoid: emoji, hashtags, buzzwords..."
            className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            onKeyDown={(e) => {
              if (e.key === "Enter" && newPeeve.trim()) {
                onPetPeevesChange([...petPeeves, newPeeve.trim()]);
                setNewPeeve("");
              }
            }}
          />
          <button
            onClick={() => {
              if (newPeeve.trim()) {
                onPetPeevesChange([...petPeeves, newPeeve.trim()]);
                setNewPeeve("");
              }
            }}
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
          >
            Add
          </button>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Grammar preferences</label>
        <div className="space-y-1">
          {GRAMMAR_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={grammarPrefs[opt] ?? false}
                onChange={(e) => onGrammarPrefsChange({ ...grammarPrefs, [opt]: e.target.checked })}
                className="rounded border-border"
              />
              {opt}
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
