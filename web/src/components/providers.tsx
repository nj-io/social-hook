"use client";

import { GatewayProvider } from "@/lib/gateway-context";
import { PipelineToasts } from "@/components/pipeline-toasts";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <GatewayProvider>
      {children}
      <PipelineToasts />
    </GatewayProvider>
  );
}
