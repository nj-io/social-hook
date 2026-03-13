"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchChannelsStatus, fetchDraft, generateMediaSpec, resendDraftNotification } from "@/lib/api";
import type { Decision, Draft } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { MediaSection } from "@/components/media-section";
import { DraftActionPanel } from "@/components/draft-action-panel";
import { useDataEvents } from "@/lib/use-data-events";
import { useBackgroundTasks } from "@/lib/use-background-tasks";

export default function DraftDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      const result = await fetchDraft(id);
      setDraft(result);
    } catch {
      // Silent refresh failure
    }
  }, [id]);

  useDataEvents(["draft"], reload);

  const { trackTask, isRunning } = useBackgroundTasks(draft?.project_id ?? "");

  const handleGenerateSpec = useCallback(async (draftId: string, mediaType: string) => {
    const res = await generateMediaSpec(draftId, mediaType);
    trackTask(res.task_id, draftId, "generate_spec");
  }, [trackTask]);

  const isGeneratingSpec = draft ? isRunning(draft.id) : false;

  const [daemonRunning, setDaemonRunning] = useState(false);
  useEffect(() => {
    fetchChannelsStatus().then((s) => setDaemonRunning(!!s.daemon_running)).catch(() => {});
  }, []);

  const [resending, setResending] = useState(false);
  const handleResend = useCallback(async () => {
    if (!draft) return;
    setResending(true);
    try {
      await resendDraftNotification(draft.id);
    } catch {
      // Silent — user can retry
    } finally {
      setResending(false);
    }
  }, [draft]);

  useEffect(() => {
    async function load() {
      try {
        const result = await fetchDraft(id);
        setDraft(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load draft");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) {
    return <p className="text-center text-muted-foreground">Loading...</p>;
  }

  if (error || !draft) {
    return (
      <div className="space-y-4">
        <Link href="/drafts" className="text-sm text-accent hover:underline">
          &larr; Back to drafts
        </Link>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error || "Draft not found"}
        </div>
      </div>
    );
  }

  const platformLabel = draft.platform === "x" ? "X (Twitter)" : draft.platform === "linkedin" ? "LinkedIn" : draft.platform;

  return (
    <div className="space-y-6">
      <Link href="/drafts" className="text-sm text-accent hover:underline">
        &larr; Back to drafts
      </Link>

      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Draft Detail</h1>
        <Badge value={draft.status} variant="status" />
        {draft.is_intro && <Badge value="INTRO" variant="system" />}
        {draft.platform === "preview" && <Badge value="Preview" variant="system" />}
        <code className="text-xs text-muted-foreground">{draft.id}</code>
        {daemonRunning && (
          <button
            onClick={handleResend}
            disabled={resending}
            className="ml-auto rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
          >
            {resending ? "Sending..." : "Resend Notification"}
          </button>
        )}
      </div>

      {/* Meta info */}
      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span>Platform: <span className="font-medium text-foreground">{platformLabel}</span></span>
        {draft.decision?.media_tool && (
          <span>Media: <span className="font-medium text-foreground">{draft.decision.media_tool}</span></span>
        )}
        <span>Created: {new Date(draft.created_at).toLocaleString()}</span>
        {draft.suggested_time && (
          <span>Scheduled: {new Date(draft.suggested_time).toLocaleString()}</span>
        )}
      </div>

      {/* Metadata pills */}
      {draft.decision && (
        <div className="flex flex-wrap gap-1.5">
          {draft.decision.episode_type && <Badge value={draft.decision.episode_type} variant="category" />}
          {draft.decision.post_category && <Badge value={draft.decision.post_category} variant="category" />}
          {draft.decision.episode_tags?.map((tag) => (
            <Badge key={tag} value={tag} variant="default" />
          ))}
        </div>
      )}

      {/* Content */}
      <div className="rounded-lg border border-border p-4">
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Content</h2>
        <p className="whitespace-pre-wrap text-sm">{draft.content}</p>
      </div>

      {/* Tweets (for thread-style posts) */}
      {draft.tweets && draft.tweets.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Thread</h2>
          {draft.tweets.map((tweet, i) => (
            <div key={tweet.id} className="rounded-lg border border-border p-3">
              <span className="text-xs text-muted-foreground">Tweet {i + 1}</span>
              <p className="mt-1 whitespace-pre-wrap text-sm">{tweet.content}</p>
            </div>
          ))}
        </div>
      )}

      {/* Media section: tool selector, spec form, upload, preview */}
      <MediaSection draft={draft} onUpdate={reload} onGenerateSpec={handleGenerateSpec} isGeneratingSpec={isGeneratingSpec} />

      {/* Reasoning */}
      {draft.reasoning && (
        <div className="rounded-lg border border-border bg-muted/50 p-4">
          <h2 className="mb-1 text-sm font-medium text-muted-foreground">AI Reasoning</h2>
          <p className="whitespace-pre-wrap text-sm">{draft.reasoning}</p>
        </div>
      )}

      {/* Evaluator Analysis */}
      {draft.decision && <EvaluatorAnalysis decision={draft.decision} />}

      {/* Action buttons */}
      <DraftActionPanel draft={draft} onUpdate={reload} />

      {/* Audit trail */}
      {draft.changes && draft.changes.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Change History</h2>
          <div className="space-y-1">
            {draft.changes.map((change) => (
              <div key={change.id} className="flex items-baseline gap-2 text-xs">
                <span className="text-muted-foreground">
                  {new Date(change.changed_at).toLocaleString()}
                </span>
                <span className="font-medium">{change.field}</span>
                <span className="text-muted-foreground">
                  {change.old_value} &rarr; {change.new_value}
                </span>
                <span className="text-muted-foreground">by {change.changed_by}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EvaluatorAnalysis({ decision }: { decision: Decision }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between p-4 text-left"
      >
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">Evaluator Analysis</h2>
          <Badge value={decision.decision} variant="decision" />
        </div>
        <span className="text-xs text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-border px-4 pb-4 pt-3">
          {decision.reasoning && (
            <div>
              <span className="text-xs font-medium text-muted-foreground">Reasoning</span>
              <p className="mt-0.5 whitespace-pre-wrap text-sm">{decision.reasoning}</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {decision.angle && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">Angle</span>
                <p className="text-sm">{decision.angle}</p>
              </div>
            )}
            {decision.episode_type && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">Episode Type</span>
                <p className="text-sm">{decision.episode_type}</p>
              </div>
            )}
            {decision.post_category && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">Post Category</span>
                <p className="text-sm">{decision.post_category}</p>
              </div>
            )}
            {decision.media_tool && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">Media Tool</span>
                <p className="text-sm">{decision.media_tool}</p>
              </div>
            )}
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>Decision: <code className="text-accent">{decision.id.slice(0, 14)}</code></span>
            <span>Commit: <code>{decision.commit_hash.slice(0, 7)}</code></span>
            <span>{new Date(decision.created_at).toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  );
}
