"use client";

import { useState } from "react";

export function MediaPreview({ paths }: { paths: string }) {
  const [error, setError] = useState(false);

  if (!paths || error) return null;

  // paths may be a JSON array string or comma-separated
  let fileList: string[];
  try {
    const parsed = JSON.parse(paths);
    fileList = Array.isArray(parsed) ? parsed : [paths];
  } catch {
    fileList = paths.split(",").map((p) => p.trim()).filter(Boolean);
  }
  if (fileList.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {fileList.map((path, i) => (
        <img
          key={i}
          src={`/api/media/${encodeURIComponent(path)}`}
          alt={`Media ${i + 1}`}
          className="max-h-48 rounded-md border border-border object-cover"
          onError={() => setError(true)}
        />
      ))}
    </div>
  );
}
