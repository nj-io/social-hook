"use client";

import { GatewayProvider } from "@/lib/gateway-context";
import { ToastProvider } from "@/lib/toast-context";
import { PipelineToasts } from "@/components/pipeline-toasts";
import { SlowTaskBanner } from "@/components/slow-task-banner";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <GatewayProvider>
      <ToastProvider>
        {children}
        <PipelineToasts />
        <SlowTaskBanner />
      </ToastProvider>
    </GatewayProvider>
  );
}
