"use client";

import { useState } from "react";

export function MediaPreview({ paths }: { paths: string }) {
  const [error, setError] = useState(false);
  const [fullscreen, setFullscreen] = useState<string | null>(null);

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
    <>
      <div className="flex flex-wrap gap-2">
        {fileList.map((path, i) => (
          <img
            key={i}
            src={`/api/media/${encodeURIComponent(path)}`}
            alt={`Media ${i + 1}`}
            className="max-h-48 cursor-pointer rounded-md border border-border object-cover transition-opacity hover:opacity-80"
            onClick={() => setFullscreen(`/api/media/${encodeURIComponent(path)}`)}
            onError={() => setError(true)}
          />
        ))}
      </div>

      {/* Fullscreen overlay */}
      {fullscreen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setFullscreen(null)}
        >
          <img
            src={fullscreen}
            alt="Media fullscreen"
            className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setFullscreen(null)}
            className="absolute right-4 top-4 rounded-full bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/20"
          >
            Close
          </button>
          <a
            href={fullscreen}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="absolute bottom-4 right-4 rounded-full bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/20"
          >
            Open in new tab
          </a>
        </div>
      )}
    </>
  );
}
