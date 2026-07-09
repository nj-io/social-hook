import { useEffect, useRef, useState } from "react";

/**
 * Local state that stays in sync with a ``MediaSpecItem.spec`` object from
 * the server.
 *
 * Returns ``[parsed, setParsed]`` — behaves like ``useState`` but resets
 * whenever the upstream ``spec`` prop changes (e.g. after a background task
 * writes a new spec and the draft reloads via WebSocket).
 *
 * The signature expects an object, not a JSON string: multi-media specs are
 * stored and served as structured ``Record<string, unknown>`` values, so no
 * ``JSON.parse`` happens at the boundary. Pass ``undefined`` for a brand-new
 * item with no spec yet.
 */
export function useSyncedSpec(
  spec: Record<string, unknown> | null | undefined,
): [Record<string, unknown>, React.Dispatch<React.SetStateAction<Record<string, unknown>>>] {
  const initial = spec ?? {};
  const [value, setValue] = useState<Record<string, unknown>>(initial);
  const prevRef = useRef(spec);

  useEffect(() => {
    if (spec !== prevRef.current) {
      prevRef.current = spec;
      setValue(spec ?? {});
    }
  }, [spec]);

  return [value, setValue];
}
