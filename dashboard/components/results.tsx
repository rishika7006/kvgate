import { ARCH, HEADLINES, LMCACHE, OFFLOAD, ROUTING } from "@/lib/results";
import { Delta, GroupedBars, Panel } from "@/components/charts";

const GREY = "#94a3b8";
const GREEN = "#10b981";
const BLUE = "#3b82f6";

function pct(n: number) {
  return `${(n * 100).toFixed(1)}%`;
}

export function Results() {
  const routingP95 = ROUTING.ttft.find((t) => t.metric === "p95")!;
  const routingP95Gain = (routingP95.roundRobin / routingP95.prefixAware).toFixed(2);
  const thrGain = (((ROUTING.throughput.prefixAware - ROUTING.throughput.roundRobin) / ROUTING.throughput.roundRobin) * 100).toFixed(0);

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className="rounded-3xl border border-edge bg-gradient-to-br from-panel/80 to-panel/40 p-8">
        <h2 className="max-w-3xl text-3xl font-bold tracking-tight text-slate-50 md:text-4xl">
          Cutting multimodal LLM latency with{" "}
          <span className="text-sky-400">KV-cache offload</span> and{" "}
          <span className="text-emerald-400">prefix-aware routing</span>
        </h2>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-slate-400">
          An open-source, OpenAI-compatible inference gateway in front of a vLLM fleet,
          benchmarked on a 7B vision-language model.
        </p>
        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          {HEADLINES.map((h) => (
            <div key={h.label} className="rounded-2xl border border-edge bg-ink/40 p-4">
              <div className="text-3xl font-bold tabular-nums text-emerald-400">{h.value}</div>
              <div className="mt-1 text-sm font-medium text-slate-200">{h.label}</div>
              <div className="mt-1 text-xs leading-snug text-slate-500">{h.sub}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Experiment 1: routing */}
      <Panel kicker="Experiment 1 · 2-GPU fleet" title="Prefix-aware routing vs round-robin">
        <p className="mb-5 text-sm leading-relaxed text-slate-400">{ROUTING.setup}</p>
        <GroupedBars
          groups={ROUTING.ttft.map((t) => t.metric)}
          series={[
            { name: "round_robin (KV-blind)", color: GREY, values: ROUTING.ttft.map((t) => t.roundRobin) },
            { name: "prefix_kv_aware", color: GREEN, values: ROUTING.ttft.map((t) => t.prefixAware) },
          ]}
          unit="TTFT ms"
          format={(n) => `${n}`}
          lowerIsBetter
        />
        <div className="mt-6 flex flex-wrap gap-3">
          <Delta>TTFT p95: {routingP95.roundRobin} → {routingP95.prefixAware} ms ({routingP95Gain}× lower)</Delta>
          <Delta>Throughput +{thrGain}%</Delta>
          <Delta>{pct(ROUTING.affinityHitRate)} routing-affinity hit rate</Delta>
          <Delta>Balanced load: {ROUTING.loadSplit.prefixAware}</Delta>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          Round-robin scatters each image across both replicas, so each one keeps re-prefilling
          roughly 6.5k vision tokens. Prefix-aware keeps each image&apos;s KV resident on a single
          replica, and a load guard preserves balance so popular images do not pile onto one replica.
        </p>
      </Panel>

      {/* Experiment 2: LMCache */}
      <Panel kicker="Experiment 2 · single GPU" title="LMCache CPU KV offload under GPU memory pressure">
        <p className="mb-5 text-sm leading-relaxed text-slate-400">{LMCACHE.setup}</p>
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Time-to-first-token</div>
            <GroupedBars
              groups={LMCACHE.rows.map((r) => r.cap)}
              series={[
                { name: "vLLM cache only", color: GREY, values: LMCACHE.rows.map((r) => r.vllmTtft) },
                { name: "+ LMCache", color: BLUE, values: LMCACHE.rows.map((r) => r.lmcacheTtft) },
              ]}
              unit="TTFT ms"
              lowerIsBetter
            />
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Throughput</div>
            <GroupedBars
              groups={LMCACHE.rows.map((r) => r.cap)}
              series={[
                { name: "vLLM cache only", color: GREY, values: LMCACHE.rows.map((r) => r.vllmThr) },
                { name: "+ LMCache", color: BLUE, values: LMCACHE.rows.map((r) => r.lmcacheThr) },
              ]}
              unit="req/s"
              format={(n) => n.toFixed(2)}
            />
          </div>
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Delta>Up to 2.0× lower TTFT</Delta>
          <Delta>+65% throughput at the tightest cap</Delta>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          These gains appear only under memory pressure. At the tightest cap, vLLM&apos;s own
          prefix-cache hit rate fell to <span className="text-amber-400">~{pct(LMCACHE.vllmPrefixHitCollapse)}</span>{" "}
          (thrashing) while CPU offload kept the multimodal KV warm. When the working set fits in
          GPU memory, the engine&apos;s own cache suffices and there is no gain.
        </p>
      </Panel>

      {/* KV offload hierarchy: where does the KV live? */}
      <Panel kicker="Experiment 3 · KV offload hierarchy" title="Where does the offloaded KV live? CPU vs Redis">
        <p className="mb-5 text-sm leading-relaxed text-slate-400">{OFFLOAD.setup}</p>
        <div className="overflow-hidden rounded-xl border border-edge">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/40 text-left text-xs uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-4 py-3">Config</th>
                <th className="px-4 py-3">TTFT p50</th>
                <th className="px-4 py-3">TTFT p95</th>
                <th className="px-4 py-3">Throughput</th>
                <th className="px-4 py-3">Memory used (proof)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {OFFLOAD.tiers.map((t) => (
                <tr key={t.key} className={t.key === "cpu" ? "bg-emerald-500/5" : ""}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-100">{t.label}</div>
                    <div className="text-xs text-slate-500">{t.dest}</div>
                  </td>
                  <td className={`px-4 py-3 tabular-nums ${t.key === "cpu" ? "font-bold text-emerald-400" : "text-slate-200"}`}>{t.ttftP50} ms</td>
                  <td className="px-4 py-3 tabular-nums text-slate-300">{t.ttftP95} ms</td>
                  <td className={`px-4 py-3 tabular-nums ${t.key === "cpu" ? "font-bold text-emerald-400" : "text-slate-300"}`}>{t.thr} req/s</td>
                  <td className="px-4 py-3">
                    {t.mem ? (
                      <span className="rounded-full bg-sky-500/15 px-2.5 py-1 text-xs font-semibold text-sky-300 ring-1 ring-sky-500/30">{t.memLabel}</span>
                    ) : (
                      <span className="text-xs text-slate-500">{t.memLabel}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-4">
          <Stat label="CPU offload TTFT" value={`${OFFLOAD.proof.cpuTtftSpeedup}× lower`} tone="good" />
          <Stat label="CPU offload throughput" value={`${OFFLOAD.proof.cpuThrSpeedup}× higher`} tone="good" />
          <Stat label="KV stored in Redis" value={`+${(OFFLOAD.proof.redisDeltaMb / 1024).toFixed(1)} GB`} tone="sky" />
          <Stat label="LMCache retrieve" value={`${OFFLOAD.proof.retrieveThroughputGbs} GB/s`} tone="sky" />
        </div>
        <p className="mt-4 text-xs leading-relaxed text-slate-500">{OFFLOAD.takeaway}</p>
      </Panel>

      {/* Architecture */}
      <Panel kicker="How it works" title="Architecture & stack">
        <div className="flex flex-col gap-3 md:flex-row md:items-stretch">
          {ARCH.flow.map((f, i) => (
            <div key={f.node} className="flex flex-1 items-center gap-3">
              <div className="flex-1 rounded-xl border border-edge bg-ink/40 p-4">
                <div className="text-sm font-semibold text-slate-100">{f.node}</div>
                <div className="mt-1 text-xs leading-snug text-slate-500">{f.desc}</div>
              </div>
              {i < ARCH.flow.length - 1 && <div className="hidden text-slate-600 md:block">→</div>}
            </div>
          ))}
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {ARCH.stack.map((t) => (
            <span key={t} className="rounded-full bg-slate-700/40 px-3 py-1 text-xs text-slate-300 ring-1 ring-edge">
              {t}
            </span>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Stat({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "sky" | "good" }) {
  const c = { default: "text-slate-100", sky: "text-sky-400", good: "text-emerald-400" }[tone];
  return (
    <div className="rounded-xl border border-edge bg-ink/40 p-4">
      <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${c}`}>{value}</div>
    </div>
  );
}
