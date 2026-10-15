import { Link } from "react-router-dom";
import { gbp, useApi } from "../api";
import ActivityFeed from "../components/ActivityFeed";
import { Card, Empty, HealthBadge, SectionTitle } from "../components/ui";
import type { Overview as OverviewT } from "../types";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <Card className="p-5">
      <p className="text-sm text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tracking-tight ${tone ?? "text-slate-900"}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </Card>
  );
}

// Guardrails the backend already enforces (see REPORT.md). This card only describes them.
const POLICY = [
  "Billed only with evidence (client message, matched time, contract clause) and confidence ≥ 0.7; otherwise held for review.",
  "One invoice per client per month.",
  "No automatic refunds or credits.",
  "Stripe test mode only.",
];

function BillingPolicy() {
  return (
    <Card className="p-5">
      <SectionTitle>Billing policy</SectionTitle>
      <ul className="space-y-2 text-sm text-slate-700">
        {POLICY.map((p) => (
          <li key={p} className="flex gap-2">
            <span className="mt-0.5 text-accent">✓</span>
            <span>{p}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function Overview() {
  const { data, error } = useApi<OverviewT>("/overview", 5000);
  if (error) return <p className="text-red-600">{error}</p>;
  if (!data) return null;
  const s = data.stats;
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="text-sm text-slate-500">Maya Chen Design · {data.period_label}</p>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Recovered" value={gbp(s.recovered_pence)} sub="Billable extra work" tone="text-amber-700" />
        <Stat label="On the house" value={gbp(s.goodwill_value_pence)} sub={`${s.goodwill_count} favour${s.goodwill_count === 1 ? "" : "s"} given`} tone="text-emerald-700" />
        <Stat label="Needs review" value={String(s.needs_review)} sub="Held back, not billed" tone={s.needs_review ? "text-red-600" : undefined} />
        <Stat
          label="Invoices raised"
          value={String(s.invoices_raised)}
          sub={`${s.invoices_paid} paid${s.invoices_failed ? ` · ${s.invoices_failed} failed` : ""}`}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <SectionTitle>Clients</SectionTitle>
          {data.clients.length === 0 && <Empty>No clients yet. Run <code>make seed</code>.</Empty>}
          {data.clients.map((c) => (
            <Link key={c.slug} to={`/clients/${c.slug}`} className="block">
              <Card className="p-5 transition hover:border-accent/40 hover:shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold">{c.name}</p>
                    <p className="text-sm text-slate-500">{c.contact_name}</p>
                  </div>
                  <HealthBadge badge={c.health_badge} />
                </div>
                <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <p className="text-slate-500">Tab this month</p>
                    <p className="font-semibold">{gbp(c.tab_total_pence)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Favours used</p>
                    <p className="font-semibold">
                      {c.favour_allowance != null ? `${c.favours_used} of ${c.favour_allowance}` : c.favours_used}
                      {c.favours_free_kind > 0 && <span className="font-normal text-emerald-700"> +{c.favours_free_kind}</span>}
                    </p>
                  </div>
                  <div>
                    <p className="text-slate-500">Decisions</p>
                    <p className="font-semibold">{c.decisions}{c.needs_review ? <span className="font-normal text-red-600"> · {c.needs_review} to review</span> : null}</p>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
          {data.unassigned_items > 0 && (
            <p className="text-sm text-slate-500">
              {data.unassigned_items} unassigned item{data.unassigned_items === 1 ? "" : "s"} (matched no client, never billed).
            </p>
          )}
        </div>
        <div className="space-y-6 lg:col-span-2">
          <BillingPolicy />
          <ActivityFeed />
        </div>
      </div>
    </div>
  );
}
