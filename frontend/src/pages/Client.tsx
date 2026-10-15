import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { gbp, londonDate, useApi } from "../api";
import GoodwillMeter from "../components/GoodwillMeter";
import HealthPanel from "../components/HealthPanel";
import RequestCard from "../components/RequestCard";
import SidePanel, { type PanelTarget } from "../components/SidePanel";
import { Card, Chip, Empty, Notice, SectionTitle, SimulatedTag, SourceIcon } from "../components/ui";
import type { ClientDetail, Term } from "../types";

function termChip(t: Term): string | null {
  const v = t.value as number;
  switch (t.key) {
    case "included_pages":
      return `${(t.value as string[]).length} pages`;
    case "revision_rounds_per_page":
      return `${v} revisions/page`;
    case "hourly_rate_pence":
      return `£${v % 100 ? (v / 100).toFixed(2) : v / 100}/h`;
    case "meetings_per_month":
      return `${v} meeting${v === 1 ? "" : "s"}/month`;
    case "meeting_max_minutes":
      return `≤ ${v} min per meeting`;
    case "billing_increment_minutes":
      return `${v}-min increments`;
    case "bug_fix_window_days":
      return `bug fixes ${v} days`;
    case "invoice_day_of_month":
      return `invoiced on day ${v}`;
    case "payment_terms_days":
      return `due in ${v} days`;
    default:
      return null;
  }
}

const STATUS_TONE = { open: "amber", paid: "green", failed: "red", void: "slate", draft: "slate" } as const;

export default function Client() {
  const { slug } = useParams();
  const [params, setParams] = useSearchParams();
  const period = params.get("period");
  const { data, error } = useApi<ClientDetail>(`/clients/${slug}${period ? `?period=${period}` : ""}`, 5000);
  const [panel, setPanel] = useState<PanelTarget | null>(null);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!data) return null;
  const c = data.client;
  return (
    <div className="space-y-6">
      <SidePanel target={panel} onClose={() => setPanel(null)} />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{c.name}</h1>
          <p className="text-sm text-slate-500">{c.contact_name} · {c.contact_email}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {data.terms.length === 0 && <Chip tone="amber">Contract terms not extracted yet{data.llm_ok ? "" : " (LLM key missing)"}</Chip>}
            {data.terms.map((t) => {
              const label = termChip(t);
              return label ? <Chip key={t.key} title={`Clause ${t.clause_ref}: ${t.source_text}`}>{label} · {t.clause_ref}</Chip> : null;
            })}
          </div>
        </div>
        <div className="flex rounded-lg bg-slate-100 p-1">
          {data.periods.map((p) => (
            <button
              key={p.period}
              onClick={() => setParams({ period: p.period })}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${p.period === data.period ? "bg-white shadow-sm" : "text-slate-600"}`}
            >
              {p.label.split(" ")[0]}{p.history ? " (history)" : ""}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <SectionTitle>Requests · {data.period_label}</SectionTitle>
          {data.is_history && (
            <Notice tone="slate">
              {data.period_label} is before Tab started keeping the tab. These items are in Cognee memory (for example, earlier revision
              rounds) but are never decided or billed.
            </Notice>
          )}
          {data.pending_items.length > 0 && (
            <Notice tone="amber">
              {data.pending_items.length} message{data.pending_items.length === 1 ? "" : "s"} waiting to be read
              {data.llm_ok ? " (processing)…" : ": LLM key missing, so Tab can't extract requests yet."}
            </Notice>
          )}
          {data.requests.map((r) => <RequestCard key={r.id} r={r} onOpen={setPanel} />)}
          {!data.is_history && data.requests.length === 0 && <Empty>No requests for this period yet.</Empty>}
          {data.pending_items.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Not read yet</p>
              {data.pending_items.map((i) => (
                <button key={i.id} onClick={() => setPanel({ kind: "source_item", id: i.id })} className="flex w-full items-start gap-3 rounded-lg border border-dashed border-slate-200 p-3 text-left hover:bg-slate-50">
                  <SourceIcon source={i.source} />
                  <div className="min-w-0">
                    <p className="text-xs text-slate-500">{i.occurred_local} · {i.author} · {i.channel} {i.simulated && <SimulatedTag />}</p>
                    <p className="truncate text-sm text-slate-700">{i.text}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
          {data.history_items.length > 0 && (
            <div className="space-y-2">
              {data.history_items.map((i) => (
                <button key={i.id} onClick={() => setPanel({ kind: "source_item", id: i.id })} className="flex w-full items-start gap-3 rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50">
                  <SourceIcon source={i.source} />
                  <div className="min-w-0">
                    <p className="text-xs text-slate-500">{i.occurred_local} · {i.author} · {i.channel} · {i.remembered_at ? "remembered" : "not yet remembered"}</p>
                    <p className="truncate text-sm text-slate-700">{i.text}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
          {data.not_requests.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-slate-500">{data.not_requests.length} message{data.not_requests.length === 1 ? "" : "s"} with no request (thanks, FYI)</summary>
              <ul className="mt-2 space-y-1">
                {data.not_requests.map((i) => (
                  <li key={i.id}>
                    <button className="text-left text-slate-600 hover:underline" onClick={() => setPanel({ kind: "source_item", id: i.id })}>
                      {londonDate(i.occurred_at)} · {i.author}: “{i.text.slice(0, 90)}”
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {data.unmatched_time.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-slate-500">{data.unmatched_time.length} time entr{data.unmatched_time.length === 1 ? "y" : "ies"} not matched to a request</summary>
              <ul className="mt-2 space-y-1 text-slate-600">
                {data.unmatched_time.map((t) => (
                  <li key={t.id}>{t.started_local} · {t.minutes} min · {t.description}{t.match_reason ? ` (${t.match_reason})` : ""}</li>
                ))}
              </ul>
            </details>
          )}
        </div>

        <div className="space-y-6">
          <Card className="p-5"><GoodwillMeter card={data.card} /></Card>
          <HealthPanel slug={c.slug} period={data.period} />
          <Card className="p-5">
            <SectionTitle>Invoices</SectionTitle>
            {data.invoices.length === 0 && <p className="text-sm text-slate-500">No invoices yet. Tab raises them on the invoice day in the contract.</p>}
            <ul className="space-y-3">
              {data.invoices.map((inv) => (
                <li key={inv.id} className="text-sm">
                  <div className="flex items-center justify-between">
                    <Link to={`/invoices/${inv.id}`} className="font-medium text-accent hover:underline">{inv.period}</Link>
                    <Chip tone={STATUS_TONE[inv.status]}>{inv.status}</Chip>
                  </div>
                  <p className="text-slate-600">{gbp(inv.total_pence)} · {gbp(inv.goodwill_value_pence)} on the house</p>
                  <div className="flex gap-3 text-xs">
                    {inv.hosted_invoice_url && <a href={inv.hosted_invoice_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">Stripe invoice ↗</a>}
                    <a href={`/proof/${inv.proof_token}`} target="_blank" rel="noreferrer" className="text-accent hover:underline">Proof page ↗</a>
                  </div>
                  {inv.error && <p className="text-xs text-red-600">{inv.error}</p>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
