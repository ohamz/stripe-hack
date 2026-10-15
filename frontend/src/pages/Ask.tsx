import { useState } from "react";
import { api, useApi } from "../api";
import { Button, Card, Chip, Notice, Pre } from "../components/ui";
import type { RecallAnswer, SettingsPayload, Status } from "../types";

const EXAMPLES = [
  "Why did you bill Acme £200?",
  "Which favours did Acme get in October?",
  "How many revision rounds has the Acme Home page had?",
];

type Turn = { question: string; client: string; answer?: RecallAnswer; error?: string };

export default function Ask() {
  const { data: settings } = useApi<SettingsPayload>("/settings");
  const { data: status } = useApi<Status>("/status");
  const [client, setClient] = useState("");
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    if (!q.trim()) return;
    setBusy(true);
    const turn: Turn = { question: q, client };
    setTurns((t) => [turn, ...t]);
    setQuestion("");
    try {
      const answer = await api.post<RecallAnswer>("/ask", { question: q, client_slug: client || null });
      setTurns((t) => t.map((x) => (x === turn ? { ...x, answer } : x)));
    } catch (e) {
      setTurns((t) => t.map((x) => (x === turn ? { ...x, error: e instanceof Error ? e.message : String(e) } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ask Tab</h1>
        <p className="text-sm text-slate-500">Answers come from Cognee memory: the contracts, the goodwill rules, every message, time entry and decision.</p>
      </div>
      {status && !status.llm.ok && <Notice tone="amber">{status.llm.message}. Ask Tab needs it to recall from memory.</Notice>}
      <Card className="p-5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
          className="flex flex-col gap-3 sm:flex-row"
        >
          <select value={client} onChange={(e) => setClient(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="">All clients</option>
            {settings?.clients.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
          </select>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about any client, invoice line or decision"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-accent focus:outline-none"
          />
          <Button type="submit" disabled={busy || !question.trim()}>{busy ? "Recalling…" : "Ask"}</Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <button key={q} onClick={() => ask(q)} disabled={busy} className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent hover:bg-emerald-100">
              {q}
            </button>
          ))}
        </div>
      </Card>
      <div className="space-y-4">
        {turns.map((t, i) => (
          <Card key={i} className="p-5">
            <p className="font-medium">{t.question}</p>
            <p className="text-xs text-slate-400">{t.client || "All clients"}</p>
            {!t.answer && !t.error && <p className="mt-3 text-sm text-slate-500">Recalling from memory…</p>}
            {t.error && <p className="mt-3 text-sm text-red-600">{t.error}</p>}
            {t.answer && (
              <div className="mt-3 space-y-3">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{t.answer.answer || "(no answer)"}</p>
                {t.answer.evidence_block && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">References</p>
                    <Pre>{t.answer.evidence_block}</Pre>
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  <Chip>{t.answer.query_type}</Chip>
                  {t.answer.datasets.map((d) => <Chip key={d} tone="green">{d}</Chip>)}
                  {t.answer.references.length > 0 && <Chip>{t.answer.references.length} structured references</Chip>}
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
