import { useEffect, useRef, useState } from "react";

/**
 * Local state that stays in sync with draft.media_spec from the server.
 *
 * Returns [parsed, setParsed] — behaves like useState but resets whenever
 * the upstream `mediaSpec` prop changes (e.g. after a background task
 * writes a new spec and the draft reloads via WebSocket).
 */
export function useSyncedSpec(
  mediaSpec: string | Record<string, unknown> | null | undefined,
): [Record<string, unknown>, React.Dispatch<React.SetStateAction<Record<string, unknown>>>] {
  const parse = (raw: typeof mediaSpec): Record<string, unknown> =>
    typeof raw === "string" ? JSON.parse(raw) : raw ?? {};

  const [spec, setSpec] = useState<Record<string, unknown>>(() => parse(mediaSpec));
  const prevRef = useRef(mediaSpec);

  useEffect(() => {
    if (mediaSpec !== prevRef.current) {
      prevRef.current = mediaSpec;
      setSpec(parse(mediaSpec));
    }
  }, [mediaSpec]);

  return [spec, setSpec];
}
