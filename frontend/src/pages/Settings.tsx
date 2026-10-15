import { useState } from "react";
import { api, londonDate, useApi } from "../api";
import { Button, Card, Chip, Notice, SectionTitle } from "../components/ui";
import type { Rule, SettingsPayload } from "../types";

const MODE_TONE: Record<string, "green" | "amber" | "red" | "slate"> = {
  Live: "green",
  "Test mode connected": "green",
  Configured: "green",
  "Demo file": "slate",
  File: "slate",
  Off: "slate",
  Missing: "amber",
  Connecting: "amber",
  "Test key set": "amber",
  Error: "red",
};

const LABELS: Record<string, string> = {
  slack: "Slack",
  email: "Email",
  calendar: "Calendar",
  timelog: "Time tracker",
  stripe: "Stripe",
  llm: "LLM (OpenAI, via Cognee)",
  payments: "Payment status",
};

function RuleRow({ rule, onSaved }: { rule: Rule; onSaved: () => void }) {
  const [text, setText] = useState(rule.text);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function save(body: Partial<Pick<Rule, "text" | "enabled">>) {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.put<{ redecided: number }>(`/settings/rules/${rule.id}`, body);
      setMsg(r.redecided ? `Saved. Re-deciding ${r.redecided} request(s)…` : "Saved.");
      onSaved();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="space-y-2 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{rule.rule_ref}</span>
        <Chip>{rule.applies_to}</Chip>
        {rule.parse_status === "parsed" && <Chip tone="green">Understood</Chip>}
        {rule.parse_status === "not_understood" && <Chip tone="red">Not understood · not applied</Chip>}
        {rule.parse_status === "pending" && <Chip tone="amber">Not parsed yet</Chip>}
        {!rule.enabled && <Chip>Disabled</Chip>}
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="w-full rounded-lg border border-slate-300 p-2 text-sm" />
      {rule.params && <p className="font-mono text-xs text-slate-500">{JSON.stringify(rule.params)}</p>}
      {rule.parse_note && <p className="text-xs text-slate-500">{rule.parse_note}</p>}
      <div className="flex items-center gap-2">
        <Button variant="secondary" disabled={busy || text.trim() === rule.text} onClick={() => save({ text })}>Save and re-parse</Button>
        <Button variant="ghost" disabled={busy} onClick={() => save({ enabled: !rule.enabled })}>{rule.enabled ? "Disable" : "Enable"}</Button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </div>
    </li>
  );
}

export default function Settings() {
  const { data, error, reload } = useApi<SettingsPayload>("/settings", 5000);
  const [clock, setClock] = useState("");
  const [sim, setSim] = useState({ client_slug: "acme", channel: "slack", text: "" });
  const [note, setNote] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setNote(null);
    try {
      await fn();
      setNote(ok);
      reload();
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    }
  }

  if (error) return <p className="text-red-600">{error}</p>;
  if (!data) return null;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <Card className="p-5">
        <SectionTitle>Integrations</SectionTitle>
        <ul className="divide-y divide-slate-100 text-sm">
          {Object.entries(data.integrations).map(([name, s]) => (
            <li key={name} className="flex items-center justify-between gap-4 py-3">
              <div>
                <p className="font-medium">{LABELS[name] ?? name}</p>
                {s.detail && <p className="text-xs text-slate-500">{s.detail}</p>}
              </div>
              <Chip tone={MODE_TONE[s.mode] ?? "slate"}>{s.mode}</Chip>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="p-5">
        <SectionTitle>Goodwill rules</SectionTitle>
        <ul className="divide-y divide-slate-100">
          {data.rules.map((r) => <RuleRow key={`${r.id}-${r.text}-${r.parse_status}`} rule={r} onSaved={reload} />)}
        </ul>
      </Card>
      <Card className="border-dashed p-5">
        <SectionTitle>Demo controls</SectionTitle>
        {note && <div className="mb-4"><Notice tone="slate">{note}</Notice></div>}
        <div className="space-y-6 text-sm">
          <div>
            <p className="font-medium">Demo clock</p>
            <p className="text-slate-500">Now: {londonDate(data.clock.now)} London {data.clock.demo_now ? "(demo clock)" : "(real time)"}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input type="datetime-local" value={clock} onChange={(e) => setClock(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1.5" />
              <Button variant="secondary" disabled={!clock} onClick={() => run(() => api.post("/demo/clock", { now: clock }), "Clock set.")}>Set clock</Button>
              <Button onClick={() => run(() => api.post("/demo/clock", { now: "2026-11-01T09:00" }), "Jumped to 1 Nov 09:00. The billing job runs now.")}>
                Jump to 1 Nov 09:00
              </Button>
              <Button variant="ghost" onClick={() => run(() => api.post("/demo/clock", { now: null }), "Back to real time.")}>Use real time</Button>
            </div>
          </div>
          <div>
            <p className="font-medium">Simulate a client message</p>
            <p className="text-slate-500">Stored as “Simulated” and labelled everywhere.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <select value={sim.client_slug} onChange={(e) => setSim({ ...sim, client_slug: e.target.value })} className="rounded-lg border border-slate-300 px-2 py-1.5">
                {data.clients.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
              <select value={sim.channel} onChange={(e) => setSim({ ...sim, channel: e.target.value })} className="rounded-lg border border-slate-300 px-2 py-1.5">
                <option value="slack">Slack</option>
                <option value="email">Email</option>
              </select>
            </div>
            <textarea value={sim.text} onChange={(e) => setSim({ ...sim, text: e.target.value })} rows={2} placeholder="Could you also make a banner for our newsletter?" className="mt-2 w-full rounded-lg border border-slate-300 p-2" />
            <Button disabled={sim.text.trim().length < 2} onClick={() => run(async () => { await api.post("/demo/simulate", sim); setSim({ ...sim, text: "" }); }, "Message stored. Watch the activity feed.")}>
              Send simulated message
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => run(() => api.post("/demo/run-pipeline"), "Pipeline started.")}>Run pipeline now</Button>
            <Button variant="secondary" onClick={() => run(() => api.post("/demo/run-billing"), "Billing job ran.")}>Run billing job now</Button>
            <Button
              variant="secondary"
              onClick={() => {
                if (confirm("Reset the demo? This wipes the database and Cognee memory, then seeds again.")) run(() => api.post("/demo/reset"), "Reset started.");
              }}
            >
              Reset demo
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
