import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    default: "text-slate-100",
    good: "text-emerald-400",
    warn: "text-amber-400",
    bad: "text-rose-400",
  }[tone];
  return (
    <div className="rounded-2xl border border-edge bg-panel/70 p-5 shadow-lg shadow-black/20">
      <div className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-2 text-3xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Pill({ children, tone = "default" }: { children: ReactNode; tone?: string }) {
  const toneClass: Record<string, string> = {
    default: "bg-slate-700/50 text-slate-200",
    good: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30",
    bad: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30",
    info: "bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${toneClass[tone] || toneClass.default}`}>
      {children}
    </span>
  );
}

export function Bar({ value, max, tone = "sky" }: { value: number; max: number; tone?: string }) {
  const pctW = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const color: Record<string, string> = {
    sky: "bg-sky-500",
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
  };
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
      <div className={`h-full ${color[tone] || color.sky}`} style={{ width: `${pctW}%` }} />
    </div>
  );
}
