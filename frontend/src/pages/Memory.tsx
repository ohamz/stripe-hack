import { useEffect, useState } from "react";
import { api, useApi } from "../api";
import { Button, Card, Notice, SectionTitle } from "../components/ui";
import type { MemoryStats } from "../types";

export default function Memory() {
  const { data, error, reload } = useApi<MemoryStats>("/memory/stats", 10000);
  const [client, setClient] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!client && data?.clients.length) setClient(data.clients[0].slug);
  }, [data, client]);

  async function refresh() {
    setBusy(true);
    setErr(null);
    try {
      await api.post(`/memory/graph/refresh?client=${client}`);
      setVersion((v) => v + 1);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="text-red-600">{error}</p>;
  if (!data) return null;
  const current = data.clients.find((c) => c.slug === client);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Memory</h1>
        <p className="text-sm text-slate-500">One Cognee dataset per client. Node sets tag where each memory came from.</p>
      </div>
      {!data.llm_ok && <Notice tone="amber">LLM key missing: nothing has been remembered yet. Counts below show what is waiting.</Notice>}
      <Card className="overflow-x-auto p-5">
        <SectionTitle>Records remembered per node set</SectionTitle>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="py-2 pr-4 font-medium">Client (dataset)</th>
              {data.node_sets.map((n) => <th key={n} className="px-2 py-2 text-right font-medium">{n}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.clients.map((c) => (
              <tr key={c.slug} className="border-t border-slate-100">
                <td className="py-2 pr-4">{c.name} <span className="text-xs text-slate-400">{c.dataset}</span></td>
                {data.node_sets.map((n) => (
                  <td key={n} className="px-2 py-2 text-right tabular-nums">
                    {c.remembered[n]}
                    {c.pending[n] > 0 && <span className="text-xs text-amber-700"> +{c.pending[n]} waiting</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-slate-400">Counted from Tab's log of successful remember() calls.</p>
      </Card>
      <Card className="p-5">
        <SectionTitle
          right={
            <div className="flex items-center gap-2">
              <select value={client} onChange={(e) => setClient(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
                {data.clients.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
              <Button variant="secondary" onClick={refresh} disabled={busy || !client}>{busy ? "Rendering…" : "Refresh graph"}</Button>
            </div>
          }
        >
          Knowledge graph
        </SectionTitle>
        {err && <Notice tone="red">{err}</Notice>}
        {current?.graph_available ? (
          <iframe key={`${client}-${version}`} title="Cognee graph" src={`/api/memory/graph.html?client=${client}&v=${version}`} className="h-[640px] w-full rounded-lg border border-slate-200" />
        ) : (
          <p className="text-sm text-slate-500">No graph rendered yet for this client. Press “Refresh graph”.</p>
        )}
      </Card>
    </div>
  );
}
