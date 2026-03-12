"use client";

import { useState } from "react";
import type { Draft } from "@/lib/types";
import { MediaToolHeader } from "./media-tool-header";
import { ToolSpecForm } from "./tool-spec-form";
import { MediaPreview } from "./media-preview";
import { UploadDropZone } from "./upload-drop-zone";
import { MediaActionBar } from "./media-action-bar";

interface MediaSectionProps {
  draft: Draft;
  onUpdate: () => void;
  onGenerateSpec: (draftId: string, mediaType: string) => void;
  isGeneratingSpec: boolean;
}

export function MediaSection({ draft, onUpdate, onGenerateSpec, isGeneratingSpec }: MediaSectionProps) {
  const [specEditing, setSpecEditing] = useState(false);

  return (
    <div className="space-y-4 rounded-lg border border-border p-4">
      <MediaToolHeader
        draft={draft}
        onUpdate={onUpdate}
        onEditSpec={() => setSpecEditing(true)}
        onGenerateSpec={onGenerateSpec}
        isGeneratingSpec={isGeneratingSpec}
      />

      {specEditing && (
        <ToolSpecForm
          draft={draft}
          onUpdate={() => { onUpdate(); setSpecEditing(false); }}
          onCancel={() => setSpecEditing(false)}
        />
      )}

      {draft.media_paths && (
        <MediaPreview paths={draft.media_paths} />
      )}

      <UploadDropZone draftId={draft.id} onUpdate={onUpdate} />

      <MediaActionBar draft={draft} onUpdate={onUpdate} />
    </div>
  );
}
