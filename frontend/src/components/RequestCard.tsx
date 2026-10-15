import { useState } from "react";
import { gbp, londonDate, minutesLabel } from "../api";
import type { EvidenceItem, RequestRow } from "../types";
import type { PanelTarget } from "./SidePanel";
import { CategoryBadge, Chip, Pre, SimulatedTag, SourceIcon } from "./ui";

export function EvidenceList({ items, onOpen }: { items: EvidenceItem[]; onOpen: (t: PanelTarget) => void }) {
  const icon = { source_item: "✉", time_entry: "⏱", clause: "§", rule: "♡" } as const;
  return (
    <ul className="space-y-1.5">
      {items.map((e, i) => {
        const clickable = e.type === "source_item" || e.type === "time_entry";
        return (
          <li key={i}>
            <button
              disabled={!clickable}
              onClick={() => clickable && onOpen({ kind: e.type as "source_item" | "time_entry", id: Number(e.id) })}
              className={`flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm ${clickable ? "hover:bg-slate-50" : "cursor-default"}`}
            >
              <span className="w-4 shrink-0 text-slate-400">{icon[e.type]}</span>
              <span className={clickable ? "text-accent underline-offset-2 hover:underline" : "text-slate-700"}>{e.label}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function RequestCard({ r, onOpen }: { r: RequestRow; onOpen: (t: PanelTarget) => void }) {
  const [open, setOpen] = useState(false);
  const d = r.decision;
  const minutes = d ? d.minutes_logged : r.meeting_minutes ?? r.time_entries.reduce((s, t) => s + t.minutes, 0);
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start gap-3">
        <SourceIcon source={r.source.source} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-slate-900">{r.summary}</p>
            {r.source.simulated && <SimulatedTag />}
            {r.is_future_work && <Chip>Future work</Chip>}
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            {londonDate(r.requested_at)} · {r.source.author} · {r.source.channel}
            {r.revision_round ? ` · revision round ${r.revision_round}` : ""}
          </p>
          <p className="mt-2 text-sm italic text-slate-600">“{r.quote}”</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {d ? <CategoryBadge category={d.category} /> : <Chip tone="amber">Not decided yet</Chip>}
            {d?.clause_refs.map((c) => <Chip key={c} title="Contract clause">§ {c}</Chip>)}
            {d?.rule_refs.map((g) => <Chip key={g} tone="green" title="Goodwill rule">{g}</Chip>)}
            <span className="text-xs text-slate-500">{minutes ? `${minutesLabel(minutes)} ${r.kind === "meeting" ? "meeting" : "logged"}` : "no time logged"}</span>
          </div>
        </div>
        <div className="shrink-0 text-right">
          {d?.category === "billable" && <p className="text-base font-semibold text-amber-700">{gbp(d.amount_pence)}</p>}
          {d?.category === "goodwill" && (
            <>
              <p className="text-base font-semibold text-emerald-700">£0.00</p>
              <p className="text-xs text-slate-500">worth {gbp(d.value_pence)}</p>
            </>
          )}
          {d && (d.category === "billable" || d.category === "goodwill") && (
            <p className="text-xs text-slate-400">{d.minutes_billed} min billed</p>
          )}
          {d && (
            <button onClick={() => setOpen(!open)} className="mt-2 text-sm font-medium text-accent hover:underline">
              {open ? "Hide" : "Why?"}
            </button>
          )}
        </div>
      </div>
      {open && d && (
        <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
          <p className="text-sm leading-relaxed text-slate-800">{d.explanation}</p>
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence</p>
            <EvidenceList items={d.evidence} onOpen={onOpen} />
          </div>
          <details className="rounded-lg bg-slate-50 p-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">What Tab remembered</summary>
            {d.cognee_query ? (
              <div className="mt-3 space-y-2">
                <p className="text-xs font-semibold text-slate-500">Cognee recall</p>
                <Pre>{d.cognee_query}</Pre>
                <p className="text-xs font-semibold text-slate-500">Returned context</p>
                <Pre>{d.cognee_context || "(empty)"}</Pre>
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-500">
                {r.kind === "meeting"
                  ? "Meetings are decided by deterministic counting against the contract terms; no recall was needed."
                  : "No recall was needed: no time was logged against this request."}
              </p>
            )}
            <p className="mt-2 text-xs text-slate-400">
              Confidence {Math.round(d.confidence * 100)}% · decision #{d.id} {d.remembered_at ? "· written back to memory" : "· not yet written back to memory"}
            </p>
          </details>
        </div>
      )}
    </div>
  );
}
