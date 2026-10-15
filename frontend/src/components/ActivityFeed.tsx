import { useApi, londonDate } from "../api";
import type { AgentEvent } from "../types";
import { Card, SectionTitle } from "./ui";

const LEVEL_DOT = { info: "bg-accent", warn: "bg-amber-500", error: "bg-red-500" };

export default function ActivityFeed({ limit = 40 }: { limit?: number }) {
  const { data, error } = useApi<AgentEvent[]>(`/events?limit=${limit}`, 3000);
  return (
    <Card className="p-5">
      <SectionTitle right={<span className="flex items-center gap-1.5 text-xs text-slate-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />Live</span>}>
        Agent activity
      </SectionTitle>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ol className="space-y-3">
        {(data ?? []).map((e) => (
          <li key={e.id} className="flex gap-3 text-sm">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${LEVEL_DOT[e.level]}`} />
            <div className="min-w-0">
              <p className={e.level === "error" ? "text-red-700" : e.level === "warn" ? "text-amber-900" : "text-slate-800"}>{e.message}</p>
              <p className="text-xs text-slate-400">{londonDate(e.ts)} · {e.type}</p>
            </div>
          </li>
        ))}
        {data && data.length === 0 && <li className="text-sm text-slate-500">No activity yet.</li>}
      </ol>
    </Card>
  );
}
