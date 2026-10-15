import { useState } from "react";
import { api, gbp, useApi } from "../api";
import type { Health } from "../types";
import { Button, Card, HealthBadge, Notice, Pre, SectionTitle } from "./ui";

export default function HealthPanel({ slug, period }: { slug: string; period: string }) {
  const { data, error, reload } = useApi<Health>(`/clients/${slug}/health?period=${period}`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setErr(null);
    try {
      await api.post(`/clients/${slug}/health/narrative?period=${period}`);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <Notice tone="red">{error}</Notice>;
  if (!data) return null;
  const n = data.numbers;
  const share = Math.min(100, n.beyond_scope_share_pct);
  return (
    <Card className="p-5">
      <SectionTitle right={data.has_decisions ? <HealthBadge badge={n.badge} /> : null}>Health · {data.period_label}</SectionTitle>
      {!data.has_decisions ? (
        <p className="text-sm text-slate-500">No decisions for this period yet, so there is nothing to report.</p>
      ) : (
        <>
          <div className="mb-2 flex justify-between text-sm">
            <span className="text-slate-600">Beyond scope</span>
            <span className="font-semibold">{n.beyond_scope_share_pct.toFixed(1)}%</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full rounded-full bg-amber-500" style={{ width: `${share}%` }} />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <dt className="text-slate-500">Hours total</dt><dd className="text-right font-medium">{n.hours_total.toFixed(2)} h</dd>
            <dt className="text-slate-500">In scope</dt><dd className="text-right font-medium">{n.hours_in_scope.toFixed(2)} h</dd>
            <dt className="text-slate-500">Beyond scope</dt><dd className="text-right font-medium">{n.hours_beyond_scope.toFixed(2)} h</dd>
            <dt className="text-slate-500">Favours used</dt><dd className="text-right font-medium">{n.favours_used}{n.favours_free_kind ? ` + ${n.favours_free_kind} always free` : ""}</dd>
            <dt className="text-slate-500">Billed</dt><dd className="text-right font-medium">{gbp(n.amount_billed_pence)}</dd>
            <dt className="text-slate-500">Needs review</dt><dd className="text-right font-medium">{n.needs_review}</dd>
          </dl>
          <div className="mt-4 border-t border-slate-100 pt-4">
            {data.narrative?.paragraph && <p className="text-sm leading-relaxed text-slate-800">{data.narrative.paragraph}</p>}
            {data.narrative?.withheld_reason && <Notice tone="amber">{data.narrative.withheld_reason}</Notice>}
            {data.narrative && (
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-slate-500">What Tab remembered</summary>
                <Pre>{data.narrative.cognee_query + "\n\n" + data.narrative.cognee_context}</Pre>
              </details>
            )}
            {!data.llm_ok && <p className="text-sm text-amber-800">LLM key missing: the recommendation paragraph can't be written yet.</p>}
            {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
            <div className="mt-3">
              <Button variant="secondary" onClick={generate} disabled={busy || !data.llm_ok}>
                {busy ? "Writing…" : data.narrative ? "Rewrite recommendation" : "Write recommendation"}
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
