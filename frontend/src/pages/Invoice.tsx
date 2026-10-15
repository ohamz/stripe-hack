import { Link, useParams } from "react-router-dom";
import { gbp, londonDate, useApi } from "../api";
import { Card, CategoryBadge, Chip, Notice, SectionTitle } from "../components/ui";
import type { InvoiceDetail } from "../types";

export default function Invoice() {
  const { id } = useParams();
  const { data, error } = useApi<InvoiceDetail>(`/invoices/${id}`, 5000);
  if (error) return <p className="text-red-600">{error}</p>;
  if (!data) return null;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Invoice · {data.client?.name} · {data.period}</h1>
          <p className="text-sm text-slate-500">Raised {londonDate(data.created_at)}</p>
        </div>
        <Chip tone={data.status === "paid" ? "green" : data.status === "failed" ? "red" : "amber"}>{data.status}</Chip>
      </div>
      {data.error && <Notice tone="red">{data.error}</Notice>}
      {data.notes.map((n, i) => <Notice key={i} tone="amber">{n}</Notice>)}
      <Card className="grid gap-4 p-5 text-sm sm:grid-cols-2">
        <div><p className="text-slate-500">Stripe invoice</p><p className="font-mono">{data.stripe_invoice_id ?? "—"}</p></div>
        <div><p className="text-slate-500">Stripe customer</p><p className="font-mono">{data.stripe_customer_id ?? "—"}</p></div>
        <div><p className="text-slate-500">Total</p><p className="text-lg font-semibold">{gbp(data.total_pence)}</p></div>
        <div><p className="text-slate-500">On the house</p><p className="text-lg font-semibold text-emerald-700">{gbp(data.goodwill_value_pence)}</p></div>
        <div className="flex gap-4 sm:col-span-2">
          {data.hosted_invoice_url && <a className="text-accent hover:underline" href={data.hosted_invoice_url} target="_blank" rel="noreferrer">Stripe hosted invoice ↗</a>}
          <a className="text-accent hover:underline" href={`/proof/${data.proof_token}`} target="_blank" rel="noreferrer">Proof page ↗</a>
        </div>
      </Card>
      <Card className="p-5">
        <SectionTitle>Lines</SectionTitle>
        <ul className="divide-y divide-slate-100">
          {data.lines.map((l) => (
            <li key={l.id} className="py-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm">{l.description}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <CategoryBadge category={l.decision.category} />
                    <span className="text-xs text-slate-400">decision #{l.decision_id} · {l.stripe_invoice_item_id ?? "listed in footer"}</span>
                    <Link to={`/clients/${data.client?.slug}?period=${data.period}`} className="text-xs text-accent hover:underline">see decision</Link>
                  </div>
                </div>
                <p className="shrink-0 font-semibold">{gbp(l.amount_pence)}</p>
              </div>
              {l.disputes.map((d) => (
                <div key={d.id} className={`mt-3 rounded-lg p-3 text-sm ${d.outcome === "escalated" ? "bg-red-50 ring-1 ring-red-200" : "bg-slate-50"}`}>
                  <p><span className="font-medium">Client:</span> {d.message}</p>
                  <p className="mt-1"><span className="font-medium">Tab:</span> {d.agent_reply}</p>
                  <p className="mt-1 text-xs text-slate-500">{d.outcome === "escalated" ? "Escalated to you · " : "Upheld · "}{d.outcome_reason}</p>
                </div>
              ))}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
