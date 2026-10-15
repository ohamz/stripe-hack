import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { londonDate, useApi } from "./api";
import { Notice } from "./components/ui";
import type { Overview as OverviewT, Status } from "./types";
import Ask from "./pages/Ask";
import Client from "./pages/Client";
import Invoice from "./pages/Invoice";
import Memory from "./pages/Memory";
import Overview from "./pages/Overview";
import Proof from "./pages/Proof";
import Settings from "./pages/Settings";

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `block rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-accent-soft text-accent" : "text-slate-600 hover:bg-slate-50"}`
      }
    >
      {children}
    </NavLink>
  );
}

function KeyBanners({ status }: { status: Status | null }) {
  if (!status) return null;
  return (
    <div className="space-y-2">
      {!status.llm.ok && (
        <Notice tone="amber">
          <strong>{status.llm.message}.</strong> Demo files are loaded, but memory (Cognee), request extraction and decisions are
          paused. Nothing on screen is made up: add the key to <code>.env</code> and run <code>make seed</code>.
        </Notice>
      )}
      {!status.stripe.ok && (
        <Notice tone="amber">
          <strong>{status.stripe.message}</strong>
        </Notice>
      )}
      {status.busy && <Notice tone="slate">{status.busy}…</Notice>}
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const { data: status } = useApi<Status>("/status", 4000);
  const { data: overview } = useApi<OverviewT>("/overview", 10000);

  if (location.pathname.startsWith("/proof/")) {
    return (
      <Routes>
        <Route path="/proof/:token" element={<Proof />} />
      </Routes>
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-slate-200 px-4 py-6 md:flex">
        <div className="mb-8 px-3">
          <p className="text-xl font-bold tracking-tight text-accent">Tab</p>
          <p className="text-xs text-slate-500">A fair tab with every client</p>
        </div>
        <nav className="space-y-1">
          <NavItem to="/">Overview</NavItem>
          <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">Clients</p>
          {(overview?.clients ?? []).map((c) => (
            <NavItem key={c.slug} to={`/clients/${c.slug}`}>{c.name}</NavItem>
          ))}
          <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">Agent</p>
          <NavItem to="/ask">Ask Tab</NavItem>
          <NavItem to="/memory">Memory</NavItem>
          <NavItem to="/settings">Settings</NavItem>
        </nav>
        {status && (
          <div className="mt-auto rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
            <p className="font-medium text-slate-600">{status.clock.demo_now ? "Demo clock" : "Clock"}</p>
            <p>{londonDate(status.clock.now)} London</p>
          </div>
        )}
      </aside>
      <main className="min-w-0 flex-1">
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 md:hidden">
          <span className="font-bold text-accent">Tab</span>
          <nav className="flex gap-3 text-sm">
            <NavLink to="/">Overview</NavLink>
            <NavLink to="/ask">Ask</NavLink>
            <NavLink to="/memory">Memory</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
        </header>
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 md:px-8">
          <KeyBanners status={status} />
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/clients/:slug" element={<Client />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/invoices/:id" element={<Invoice />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<p className="text-slate-500">Page not found.</p>} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
