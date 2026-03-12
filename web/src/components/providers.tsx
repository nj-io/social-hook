"use client";

import { GatewayProvider } from "@/lib/gateway-context";
import { PipelineToasts } from "@/components/pipeline-toasts";
import { SlowTaskBanner } from "@/components/slow-task-banner";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <GatewayProvider>
      {children}
      <PipelineToasts />
      <SlowTaskBanner />
    </GatewayProvider>
  );
}
