"use client";

import { useState } from "react";
import { ErrorFeed } from "@/components/error-feed";
import { EventLog } from "@/components/event-log";

export default function SystemPage() {
  const [errorsOpen, setErrorsOpen] = useState(true);
  const [eventsOpen, setEventsOpen] = useState(true);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System</h1>
        <p className="text-muted-foreground">System health, error monitoring, and pipeline events.</p>
      </div>

      <div className="space-y-4">
        <button
          onClick={() => setErrorsOpen(!errorsOpen)}
          className="flex items-center gap-2 text-sm font-semibold hover:text-accent"
        >
          <span className={`transition-transform ${errorsOpen ? "rotate-90" : ""}`}>&#x25B6;</span>
          Recent Errors
        </button>
        {errorsOpen && <ErrorFeed />}
      </div>

      <div className="space-y-4">
        <button
          onClick={() => setEventsOpen(!eventsOpen)}
          className="flex items-center gap-2 text-sm font-semibold hover:text-accent"
        >
          <span className={`transition-transform ${eventsOpen ? "rotate-90" : ""}`}>&#x25B6;</span>
          Event Log
        </button>
        {eventsOpen && <EventLog />}
      </div>
    </div>
  );
}
