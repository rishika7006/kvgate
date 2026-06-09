// Benchmark results baked in at build time (sourced from the raw JSONs in /results).
// This lets the Results dashboard render with zero backend — ideal for a static Vercel deploy.
// Numbers are the real measured values; see docs/BENCHMARK_REPORT.md for methodology.

export type Headline = { value: string; label: string; sub: string };

export const HEADLINES: Headline[] = [
  { value: "1.84×", label: "Lower tail latency", sub: "TTFT p95, prefix-aware routing vs round-robin" },
  { value: "2.0×", label: "Lower TTFT", sub: "LMCache CPU KV offload under GPU memory pressure" },
  { value: "98.6%", label: "Routing-affinity hit rate", sub: "requests landed on the warm replica" },
  { value: "+65%", label: "Peak throughput gain", sub: "LMCache at the tightest GPU KV cap" },
];

// ---- Experiment 1: smart routing on a 2-GPU fleet ----
export const ROUTING = {
  setup:
    "Two Llava-OneVision-7B replicas, one per GPU (2× A40). Each replica's GPU KV cache is " +
    "capped so the 12 distinct 1024×1024 images can't all stay resident. 120 requests, concurrency 8.",
  ttft: [
    { metric: "p50", roundRobin: 568, prefixAware: 434 },
    { metric: "p95", roundRobin: 2783, prefixAware: 1516 },
    { metric: "p99", roundRobin: 3642, prefixAware: 2662 },
  ],
  throughput: { roundRobin: 2.69, prefixAware: 3.06 },
  affinityHitRate: 0.986,
  loadSplit: { roundRobin: "72 / 72", prefixAware: "73 / 71" },
};

// ---- Experiment 2: LMCache multimodal CPU KV offload under memory pressure ----
export const LMCACHE = {
  setup:
    "Single A40, Llava-OneVision-7B, 40 distinct 1024×1024 images, 80 requests. The GPU KV cache " +
    "is capped to force the working set to overflow GPU memory — the regime CPU offload exists for.",
  rows: [
    { cap: "KV cap 3072", vllmTtft: 855, lmcacheTtft: 422, vllmThr: 1.18, lmcacheThr: 1.37 },
    { cap: "KV cap 2560", vllmTtft: 1426, lmcacheTtft: 902, vllmThr: 0.92, lmcacheThr: 1.52 },
  ],
  // measured: at the 2560 cap, vLLM's own prefix-cache hit rate collapsed to ~41% (thrashing),
  // while LMCache kept TTFT low by serving KV from CPU. Exact hit/miss counts come from the
  // dedicated stat-logging run (see MEMORY_PROOF).
  vllmPrefixHitCollapse: 0.41,
};

// ---- Direct CPU-offload proof (filled from the dedicated stat-logging GPU run) ----
// Until that run lands, this stays null and the UI shows the config + "measuring" note.
export type MemoryProof = {
  gpuKvTokens: number;       // GPU KV capacity at the cap
  cpuKvBytesUsed: number;    // bytes LMCache actually stored to CPU RAM
  cpuRamBeforeMb: number;
  cpuRamAfterMb: number;
  kvStoredTokens: number;
  kvRetrievedTokens: number;
};
export const MEMORY_PROOF: MemoryProof | null = null;

export const ARCH = {
  stack: ["FastAPI", "vLLM 0.11", "LMCache 0.3.7", "Redis", "Prometheus", "Grafana", "Next.js 14", "Docker"],
  flow: [
    { node: "Client", desc: "OpenAI-compatible request (text + image)" },
    { node: "InferGate gateway", desc: "hashes prefix incl. image bytes → picks warm replica" },
    { node: "vLLM replica fleet", desc: "GPU prefix cache + LMCache CPU KV offload" },
  ],
};
