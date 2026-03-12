"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchConfig } from "@/lib/api";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";
import { TopBanner } from "@/components/top-banner";

const STORAGE_KEY = "slow-task-banner";
const SLOW_THRESHOLD_MS = 13_000;

interface BannerState {
  dismiss_count: number;
  dismissed_forever?: boolean;
}

function loadBannerState(): BannerState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore parse errors */ }
  return { dismiss_count: 0 };
}

function saveBannerState(state: BannerState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

/**
 * Self-contained banner for Claude CLI users. Shows after a background task
 * has been running for 13+ seconds, suggesting the user add their own API key.
 *
 * Dismiss behavior escalates: after 2 dismissals, a "Don't show again" option
 * appears. Permanent dismissal is stored in localStorage.
 */
export function SlowTaskBanner() {
  const [visible, setVisible] = useState(false);
  const [isCliUser, setIsCliUser] = useState(false);
  const [bannerState, setBannerState] = useState<BannerState>({ dismiss_count: 0 });
  const taskStartRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { addListener, removeListener } = useGateway();

  // Check if user has claude-cli models configured
  useEffect(() => {
    fetchConfig()
      .then(({ config }) => {
        const models = config?.models as Record<string, string> | undefined;
        if (models) {
          const usesCli = Object.values(models).some(
            (m) => typeof m === "string" && m.startsWith("claude-cli/"),
          );
          setIsCliUser(usesCli);
        }
      })
      .catch(() => {});
    setBannerState(loadBannerState());
  }, []);

  const dismiss = useCallback(() => {
    setVisible(false);
    const next = { ...bannerState, dismiss_count: bannerState.dismiss_count + 1 };
    setBannerState(next);
    saveBannerState(next);
  }, [bannerState]);

  const dismissForever = useCallback(() => {
    setVisible(false);
    const next = { ...bannerState, dismissed_forever: true };
    setBannerState(next);
    saveBannerState(next);
  }, [bannerState]);

  // Listen for task events
  useEffect(() => {
    if (!isCliUser || bannerState.dismissed_forever) return;

    const handler = (envelope: GatewayEnvelope) => {
      if (envelope.type !== "event") return;
      const payload = envelope.payload as Record<string, unknown>;
      if (payload.type !== "data_change") return;
      const data = payload.data as DataChangeEvent | undefined;
      if (!data || data.entity !== "task") return;

      if (data.action === "started" || data.action === "created") {
        taskStartRef.current = Date.now();
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
          if (taskStartRef.current && Date.now() - taskStartRef.current >= SLOW_THRESHOLD_MS) {
            setVisible(true);
          }
        }, SLOW_THRESHOLD_MS);
      } else if (data.action === "completed" || data.action === "failed") {
        taskStartRef.current = null;
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
      }
    };

    addListener("slow-task-banner", handler);
    return () => {
      removeListener("slow-task-banner");
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isCliUser, bannerState.dismissed_forever, addListener, removeListener]);

  if (bannerState.dismissed_forever) return null;

  return (
    <TopBanner
      visible={visible}
      onDismiss={dismiss}
      onDismissForever={bannerState.dismiss_count >= 2 ? dismissForever : undefined}
    >
      Tasks run faster with your own API key. Add one in Settings &rarr; API Keys.
    </TopBanner>
  );
}
