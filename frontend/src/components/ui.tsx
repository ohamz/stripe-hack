import type { ReactNode } from "react";
import type { Category } from "../types";

export const CATEGORY: Record<Category, { label: string; cls: string; dot: string }> = {
  included: { label: "Included", cls: "bg-slate-100 text-slate-700 ring-slate-200", dot: "bg-slate-500" },
  goodwill: { label: "On the house", cls: "bg-emerald-50 text-emerald-800 ring-emerald-200", dot: "bg-emerald-600" },
  billable: { label: "Billable", cls: "bg-amber-50 text-amber-800 ring-amber-200", dot: "bg-amber-500" },
  needs_review: { label: "Needs review", cls: "bg-red-50 text-red-700 ring-red-200", dot: "bg-red-500" },
  no_work_logged: { label: "No time logged", cls: "bg-gray-50 text-gray-500 ring-gray-200", dot: "bg-gray-300" },
};

export function CategoryBadge({ category }: { category: Category }) {
  const c = CATEGORY[category];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${c.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}

export function Chip({ children, title, tone = "slate" }: { children: ReactNode; title?: string; tone?: "slate" | "green" | "amber" | "red" }) {
  const tones = {
    slate: "bg-slate-50 text-slate-600 ring-slate-200",
    green: "bg-accent-soft text-accent ring-emerald-200",
    amber: "bg-amber-50 text-amber-800 ring-amber-200",
    red: "bg-red-50 text-red-700 ring-red-200",
  };
  return (
    <span title={title} className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function SimulatedTag() {
  return <Chip tone="amber" title="Created with the demo controls, not a real message">Simulated</Chip>;
}

const SOURCE_ICON: Record<string, string> = {
  slack: "#",
  email: "✉",
  calendar: "◷",
  timelog: "⏱",
  contract: "§",
  rules: "♡",
  simulated: "✎",
};

export function SourceIcon({ source }: { source: string }) {
  return (
    <span
      title={source}
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-sm font-semibold text-slate-600"
    >
      {SOURCE_ICON[source] ?? "•"}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-slate-200 bg-white ${className}`}>{children}</div>;
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{children}</h2>
      {right}
    </div>
  );
}

export function Notice({ tone = "amber", children }: { tone?: "amber" | "red" | "slate" | "green"; children: ReactNode }) {
  const tones = {
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    red: "border-red-200 bg-red-50 text-red-800",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    green: "border-emerald-200 bg-accent-soft text-accent-dark",
  };
  return <div className={`rounded-lg border px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>;
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
}) {
  const styles = {
    primary: "bg-accent text-white hover:bg-accent-dark disabled:bg-slate-300",
    secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
    ghost: "text-accent hover:bg-accent-soft disabled:text-slate-400",
  };
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed ${styles[variant]}`}
    >
      {children}
    </button>
  );
}

export function HealthBadge({ badge }: { badge: string | null }) {
  if (!badge) return <Chip>No decisions yet</Chip>;
  const tone = badge === "Healthy" ? "green" : badge === "Watch" ? "amber" : "red";
  return <Chip tone={tone}>{badge}</Chip>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-slate-200 px-6 py-10 text-center text-sm text-slate-500">{children}</div>;
}

export function Pre({ children }: { children: ReactNode }) {
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700">
      {children}
    </pre>
  );
}
