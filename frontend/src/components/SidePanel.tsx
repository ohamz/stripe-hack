import { useEffect, useState } from "react";
import { api } from "../api";
import type { SourceItem, TimeEntry } from "../types";
import { Chip, Pre, SimulatedTag, SourceIcon } from "./ui";

export type PanelTarget = { kind: "source_item"; id: number } | { kind: "time_entry"; id: number } | { kind: "text"; title: string; body: string };

type TimeEntryWithItem = TimeEntry & { source_item: SourceItem };

/** Slide-over that shows the raw evidence behind an item. */
export default function SidePanel({ target, onClose }: { target: PanelTarget | null; onClose: () => void }) {
  const [item, setItem] = useState<SourceItem | null>(null);
  const [entry, setEntry] = useState<TimeEntryWithItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItem(null);
    setEntry(null);
    setError(null);
    if (!target) return;
    if (target.kind === "source_item") api.get<SourceItem>(`/source-items/${target.id}`).then(setItem).catch((e) => setError(e.message));
    if (target.kind === "time_entry") api.get<TimeEntryWithItem>(`/time-entries/${target.id}`).then(setEntry).catch((e) => setError(e.message));
  }, [target]);

  if (!target) return null;
  const shown = item ?? entry?.source_item ?? null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/20" onClick={onClose}>
      <aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold">{target.kind === "text" ? target.title : "Raw evidence"}</h3>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close">✕</button>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {target.kind === "text" && <Pre>{target.body}</Pre>}
        {entry && (
          <div className="mb-4 rounded-lg bg-slate-50 p-3 text-sm">
            <p className="font-medium">{entry.minutes} min · {entry.description}</p>
            <p className="text-slate-500">{entry.started_local} · project {entry.project}</p>
            {entry.match_reason && (
              <p className="mt-2 text-slate-600">
                Match: {entry.match_reason} {entry.match_confidence != null && <>({Math.round(entry.match_confidence * 100)}% confident)</>}
              </p>
            )}
          </div>
        )}
        {shown && (
          <div className="space-y-4 text-sm">
            <div className="flex items-start gap-3">
              <SourceIcon source={shown.source} />
              <div>
                <p className="font-medium">{shown.author} {shown.simulated && <SimulatedTag />}</p>
                <p className="text-slate-500">{shown.occurred_local} Europe/London · {shown.channel}</p>
              </div>
            </div>
            {shown.title && shown.source === "email" && <p className="font-medium">Subject: {shown.title}</p>}
            <Pre>{shown.text}</Pre>
            <div className="flex flex-wrap gap-2">
              <Chip>{shown.source}:{shown.external_id}</Chip>
              {shown.cognee_dataset && <Chip tone="green">dataset {shown.cognee_dataset}</Chip>}
              {shown.cognee_node_set.length > 0 && <Chip>node set [{shown.cognee_node_set.join(", ")}]</Chip>}
              <Chip tone={shown.remembered_at ? "green" : "amber"}>{shown.remembered_at ? "Remembered in Cognee" : "Not yet remembered"}</Chip>
            </div>
            <details>
              <summary className="cursor-pointer text-slate-500">Raw JSON</summary>
              <Pre>{JSON.stringify(shown.raw, null, 2)}</Pre>
            </details>
          </div>
        )}
      </aside>
    </div>
  );
}
