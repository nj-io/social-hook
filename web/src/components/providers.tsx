"use client";

import { GatewayProvider } from "@/lib/gateway-context";
import { ToastProvider } from "@/lib/toast-context";
import { PipelineToasts } from "@/components/pipeline-toasts";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <GatewayProvider>
      <ToastProvider>
        {children}
        <PipelineToasts />
      </ToastProvider>
    </GatewayProvider>
  );
}
