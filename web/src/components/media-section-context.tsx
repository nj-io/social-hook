"use client";

import { createContext, useContext } from "react";
import type { BackgroundTask } from "@/lib/api";

interface MediaTasks {
  trackTask: (
    taskId: string,
    refId: string,
    type: string,
    opts?: { timeoutMs?: number },
  ) => void;
  isRunning: (refId: string) => boolean;
  getTask: (refId: string) => BackgroundTask | null;
}

const MediaTasksContext = createContext<MediaTasks | null>(null);

export const MediaTasksProvider = MediaTasksContext.Provider;

export function useMediaTasks(): MediaTasks {
  const ctx = useContext(MediaTasksContext);
  if (!ctx) {
    throw new Error("useMediaTasks must be used inside MediaTasksProvider");
  }
  return ctx;
}
