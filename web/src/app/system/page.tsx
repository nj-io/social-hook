"use client";

import { ErrorFeed } from "@/components/error-feed";

export default function SystemPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System</h1>
        <p className="text-muted-foreground">System health and error monitoring.</p>
      </div>
      <ErrorFeed />
    </div>
  );
}
