"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  type AdminStats,
  type ParsedMetrics,
  fetchSnapshot,
  gatewayUrl,
  pct,
  ratio,
} from "@/lib/api";
import { Bar, Pill, StatCard } from "@/components/widgets";

const POLL_MS = 2000;

export default function Dashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [metrics, setMetrics] = useState<ParsedMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const tick = useCallback(async () => {
    try {
      const snap = await fetchSnapshot();
      setStats(snap.stats);
      setMetrics(snap.metrics);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    tick();
    timer.current = setInterval(tick, POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [tick]);

  const cacheHits = metrics ? (metrics.cache.exact_hit || 0) + (metrics.cache.semantic_hit || 0) : 0;
  const cacheTotal = metrics ? cacheHits + (metrics.cache.miss || 0) : 0;
  const affWarm = metrics?.affinity.warm || 0;
  const affTotal = affWarm + (metrics?.affinity.cold || 0);
  const deployments = stats ? Object.values(stats.models).flat() : [];
  const maxReq = Math.max(1, ...deployments.map((d) => d.total_requests));

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            🚪 InferGate <span className="text-slate-400">Dashboard</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {gatewayUrl()} ·{" "}
            {error ? (
              <span className="text-rose-400">disconnected — {error}</span>
            ) : (
              <span className="text-emerald-400">
                live · updated {updatedAt ? new Date(updatedAt).toLocaleTimeString() : "…"}
              </span>
            )}
          </p>
        </div>
        {stats && (
          <div className="flex flex-wrap gap-2">
            <Pill tone="info">strategy: {stats.routing_strategy}</Pill>
            <Pill tone={stats.cache.enabled ? "good" : "default"}>
              cache: {stats.cache.enabled ? stats.cache.backend : "off"}
            </Pill>
            <Pill tone={stats.rate_limit.enabled ? "good" : "default"}>
              rate-limit: {stats.rate_limit.enabled ? `${stats.rate_limit.default_rpm} rpm` : "off"}
            </Pill>
          </div>
        )}
      </header>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Total requests" value={metrics ? metrics.totalRequests.toLocaleString() : "—"} />
        <StatCard
          label="Cache hit rate"
          value={pct(ratio(cacheHits, cacheTotal))}
          sub={`${cacheHits} hits / ${cacheTotal} lookups`}
          tone="good"
        />
        <StatCard
          label="Routing affinity (warm)"
          value={pct(ratio(affWarm, affTotal))}
          sub={affTotal ? `${affWarm} warm / ${affTotal}` : "prefix_kv_aware only"}
          tone="good"
        />
        <StatCard
          label="Tokens (prompt / completion)"
          value={
            metrics
              ? `${(metrics.tokens.prompt || 0).toLocaleString()} / ${(metrics.tokens.completion || 0).toLocaleString()}`
              : "—"
          }
        />
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
          Deployments (replicas)
        </h2>
        <div className="overflow-hidden rounded-2xl border border-edge bg-panel/70">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/40 text-left text-xs uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Upstream model</th>
                <th className="px-4 py-3">In-flight</th>
                <th className="px-4 py-3">EWMA latency</th>
                <th className="px-4 py-3">Requests</th>
                <th className="px-4 py-3">Failures</th>
                <th className="px-4 py-3">Circuit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {deployments.map((d) => (
                <tr key={`${d.provider}-${d.upstream_model}`} className="hover:bg-slate-800/20">
                  <td className="px-4 py-3 font-medium">{d.provider}</td>
                  <td className="px-4 py-3 text-slate-400">{d.upstream_model}</td>
                  <td className="px-4 py-3 tabular-nums">{d.in_flight}</td>
                  <td className="px-4 py-3 tabular-nums">{d.ewma_latency_ms.toFixed(1)} ms</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="w-12 tabular-nums">{d.total_requests}</span>
                      <div className="w-28">
                        <Bar value={d.total_requests} max={maxReq} tone="emerald" />
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{d.total_failures}</td>
                  <td className="px-4 py-3">
                    <Pill tone={d.circuit_open ? "bad" : "good"}>
                      {d.circuit_open ? "open" : "closed"}
                    </Pill>
                  </td>
                </tr>
              ))}
              {deployments.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    {error ? "No connection to the gateway." : "Waiting for data…"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="mt-10 text-center text-xs text-slate-600">
        Polls <code>/admin/stats</code> and <code>/metrics</code> every {POLL_MS / 1000}s · set
        <code className="mx-1">NEXT_PUBLIC_GATEWAY_URL</code> to point at your gateway.
      </footer>
    </main>
  );
}
