import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, gbp, minutesLabel, useApi } from "../api";
import type { Dispute, Proof as ProofT, ProofLine } from "../types";

function DisputeBox({ token, line, onDone }: { token: string; line: ProofLine; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    setErr(null);
    try {
      await api.post<Dispute>(`/proof/${token}/disputes`, { line_id: line.line_id, message: msg });
      setMsg("");
      setOpen(false);
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3">
      {line.disputes.map((d) => (
        <div key={d.id} className="mb-3 space-y-2 rounded-lg bg-slate-50 p-3 text-sm">
          <p><span className="font-medium">You asked:</span> {d.message}</p>
          <p className={d.outcome === "escalated" ? "text-slate-700" : "text-slate-800"}>
            <span className="font-medium">Reply:</span> {d.agent_reply}
          </p>
        </div>
      ))}
      {!open ? (
        <button onClick={() => setOpen(true)} className="text-sm font-medium text-[#1f5a3d] hover:underline">Question this line</button>
      ) : (
        <div className="space-y-2">
          <textarea
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            rows={3}
            placeholder="What would you like to ask about this line?"
            className="w-full rounded-lg border border-slate-300 p-3 text-sm focus:border-[#1f5a3d] focus:outline-none"
          />
          {err && <p className="text-sm text-red-600">{err}</p>}
          <div className="flex gap-2">
            <button onClick={send} disabled={busy || msg.trim().length < 2} className="rounded-lg bg-[#1f5a3d] px-3.5 py-2 text-sm font-medium text-white disabled:bg-slate-300">
              {busy ? "Checking the records…" : "Send"}
            </button>
            <button onClick={() => setOpen(false)} className="rounded-lg px-3.5 py-2 text-sm text-slate-600 hover:bg-slate-100">Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

function ExtraLine({ token, line, onDone }: { token: string; line: ProofLine; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const ev = line.evidence;
  return (
    <li className="py-5">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm text-slate-800">{line.description}</p>
        <p className="shrink-0 font-semibold">{gbp(line.amount_pence)}</p>
      </div>
      <button onClick={() => setOpen(!open)} className="mt-2 text-sm text-slate-500 hover:text-slate-800">
        {open ? "Hide evidence" : "Show evidence"}
      </button>
      {open && (
        <div className="mt-3 space-y-3 rounded-lg border border-slate-200 p-4 text-sm">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Your message</p>
            <p className="mt-1 italic text-slate-700">“{ev.message.quote}”</p>
            <p className="text-xs text-slate-500">
              {ev.message.author} · {ev.message.date} · {ev.message.source} · {ev.message.channel}
              {ev.message.simulated && " · Simulated"}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Time</p>
            {ev.time.map((t, i) => <p key={i} className="text-slate-700">{t.date} · {minutesLabel(t.minutes)} · {t.description}</p>)}
            <p className="text-xs text-slate-500">{ev.minutes_logged} min logged, {ev.minutes_billed} min billed</p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Contract</p>
            {ev.clauses.map((c) => <p key={c.ref} className="text-slate-700"><span className="font-medium">Clause {c.ref}.</span> {c.text}</p>)}
          </div>
          <p className="text-slate-600">{ev.explanation}</p>
        </div>
      )}
      <DisputeBox token={token} line={line} onDone={onDone} />
    </li>
  );
}

export default function Proof() {
  const { token = "" } = useParams();
  const { data, error, reload } = useApi<ProofT>(`/proof/${token}`, 10000);
  if (error) return <div className="mx-auto max-w-2xl p-10 text-slate-600">{error}</div>;
  if (!data) return null;
  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-2xl px-5 py-12">
        <p className="text-sm font-medium text-[#1f5a3d]">{data.business_name}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          Invoice for {data.period_label} · {gbp(data.total_pence)}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          For {data.client_name} · Status: <span className="font-medium capitalize text-slate-700">{data.status}</span>
        </p>
        {data.hosted_invoice_url && data.status !== "paid" && (
          <a href={data.hosted_invoice_url} target="_blank" rel="noreferrer" className="mt-6 inline-flex rounded-lg bg-[#1f5a3d] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#163f2b]">
            Pay invoice
          </a>
        )}
        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Extra work</h2>
          <p className="mt-1 text-sm text-slate-500">Work outside the contract, with the evidence for every line.</p>
          <ul className="divide-y divide-slate-100">
            {data.extra_work.map((l) => <ExtraLine key={l.line_id} token={token} line={l} onDone={reload} />)}
          </ul>
        </section>
        {data.on_the_house.length > 0 && (
          <section className="mt-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">On the house</h2>
            <p className="mt-1 text-sm text-slate-500">Worth {gbp(data.goodwill_value_pence)} in total. No charge.</p>
            <ul className="mt-3 space-y-3">
              {data.on_the_house.map((l) => (
                <li key={l.line_id} className="rounded-lg bg-emerald-50 p-4 text-sm">
                  <div className="flex justify-between gap-4">
                    <p className="text-slate-800">{l.summary}</p>
                    <p className="shrink-0 text-emerald-800">worth {gbp(l.value_pence)}</p>
                  </div>
                  <p className="mt-1 text-xs text-emerald-800">Included free as a favour, no charge.</p>
                </li>
              ))}
            </ul>
          </section>
        )}
        <p className="mt-12 text-xs text-slate-400">Prepared by Tab for {data.freelancer_name}.</p>
      </div>
    </div>
  );
}
