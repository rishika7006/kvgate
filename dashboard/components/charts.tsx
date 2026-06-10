import type { ReactNode } from "react";

// A grouped vertical bar chart rendered with plain divs (no chart lib, deploys anywhere).
// Bars use explicit pixel heights against a fixed chart height so they always render.
export function GroupedBars({
  groups,
  series,
  unit = "",
  format = (n: number) => `${n}`,
  lowerIsBetter = false,
}: {
  groups: string[];
  series: { name: string; color: string; values: number[] }[];
  unit?: string;
  format?: (n: number) => string;
  lowerIsBetter?: boolean;
}) {
  const CHART_H = 180;
  const max = Math.max(...series.flatMap((s) => s.values)) * 1.2 || 1;
  return (
    <div>
      <div className="flex items-end gap-10 px-2" style={{ height: CHART_H }}>
        {groups.map((g, gi) => (
          <div key={g} className="flex flex-1 items-end justify-center gap-3" style={{ height: CHART_H }}>
            {series.map((s) => {
              const v = s.values[gi];
              const px = Math.max(4, Math.round((v / max) * CHART_H));
              return (
                <div key={s.name} className="flex flex-col items-center justify-end" style={{ width: 56 }}>
                  <div className="mb-1 text-xs font-semibold tabular-nums text-slate-200">{format(v)}</div>
                  <div className="w-full rounded-t-md" style={{ height: px, background: s.color }} />
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-10 border-t border-edge px-2 pt-2">
        {groups.map((g) => (
          <div key={g} className="flex-1 text-center text-xs font-medium text-slate-400">{g}</div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-4">
        {series.map((s) => (
          <div key={s.name} className="flex items-center gap-2 text-xs text-slate-300">
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: s.color }} />
            {s.name}
          </div>
        ))}
        {unit && <span className="text-xs text-slate-500">({unit}{lowerIsBetter ? ", lower is better" : ""})</span>}
      </div>
    </div>
  );
}

export function Panel({ title, kicker, children }: { title: string; kicker?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-edge bg-panel/60 p-6 shadow-lg shadow-black/20">
      {kicker && <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-sky-400">{kicker}</div>}
      <h3 className="mb-4 text-lg font-semibold text-slate-100">{title}</h3>
      {children}
    </section>
  );
}

// A horizontal "improvement" delta chip.
export function Delta({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-500/30">
      {children}
    </span>
  );
}
