// Benchmark results baked in at build time (sourced from the raw JSONs in /results).
// This lets the Results dashboard render with zero backend, ideal for a static Vercel deploy.
// Numbers are the real measured values; see docs/BENCHMARK_REPORT.md for methodology.

export type Headline = { value: string; label: string; sub: string };

export const HEADLINES: Headline[] = [
  { value: "1.84×", label: "Lower tail latency", sub: "Tail latency (TTFT p95) versus round-robin routing" },
  { value: "2.0×", label: "Lower TTFT", sub: "Time-to-first-token with CPU KV offload under memory pressure" },
  { value: "98.6%", label: "Routing-affinity hit rate", sub: "Requests routed to a replica with the cache already warm" },
  { value: "+65%", label: "Peak throughput gain", sub: "Throughput under the tightest memory cap" },
];

// ---- Experiment 1: smart routing on a 2-GPU fleet ----
export const ROUTING = {
  setup:
    "Two Llava-OneVision-7B replicas, one per GPU. Each replica's GPU KV cache is capped so the " +
    "12 distinct 1024×1024 images cannot all stay resident. 120 requests, concurrency 8.",
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
    "Llava-OneVision-7B, 40 distinct 1024×1024 images, 80 requests. The GPU KV cache is capped to " +
    "force the working set to overflow GPU memory, the regime CPU offload is built for.",
  rows: [
    { cap: "KV cap 3072", vllmTtft: 855, lmcacheTtft: 422, vllmThr: 1.18, lmcacheThr: 1.37 },
    { cap: "KV cap 2560", vllmTtft: 1426, lmcacheTtft: 902, vllmThr: 0.92, lmcacheThr: 1.52 },
  ],
  // measured: at the 2560 cap, vLLM's own prefix-cache hit rate collapsed to ~41% (thrashing),
  // while LMCache kept TTFT low by serving KV from CPU. Exact hit/miss counts come from the
  // dedicated stat-logging run (see MEMORY_PROOF).
  vllmPrefixHitCollapse: 0.41,
};

// ---- KV-offload hierarchy: where does the KV live? (measured) ----
// Same workload (40 distinct 1024px images, 80 reqs, GPU KV capped), three LMCache configs run
// back-to-back. CPU offload is the latency win; Redis is not faster (loopback here), its value
// is capacity + cross-host KV sharing.
export const OFFLOAD = {
  setup:
    "Llava-OneVision-7B, 40 distinct 1024×1024 images, 80 requests, with the GPU KV cache capped " +
    "to force overflow. Three LMCache configurations, identical workload.",
  tiers: [
    { key: "control", label: "GPU only (baseline)", dest: "recompute on evict", ttftP50: 1393, ttftP95: 2583, thr: 1.11, memLabel: "none", mem: null },
    { key: "cpu", label: "+ LMCache → CPU RAM", dest: "local_cpu: true", ttftP50: 249, ttftP95: 412, thr: 2.33, memLabel: "CPU RAM +35 GB", mem: "cpu" },
    { key: "redis", label: "+ LMCache → Redis (direct)", dest: "local_cpu: false", ttftP50: 1424, ttftP95: 2686, thr: 1.08, memLabel: "Redis +4.7 GB", mem: "redis" },
  ],
  // direct evidence the offload tiers actually used the storage
  proof: {
    cpuRamDeltaMb: 34950,     // CPU RAM rose ~35 GB when offloading to CPU
    redisDeltaMb: 4739,       // Redis used_memory: 1 MB -> 4740 MB when offloading to Redis
    storeThroughputGbs: 12.7, // LMCache logged store throughput
    retrieveThroughputGbs: 22.1,
    cpuTtftSpeedup: 5.6,      // 1393 -> 249 ms
    cpuThrSpeedup: 2.1,       // 1.11 -> 2.33 req/s
  },
  takeaway:
    "CPU offload cut TTFT 5.6× and doubled throughput, consuming about 35 GB of CPU RAM (LMCache " +
    "logged 13 to 22 GB/s store and retrieve). Redis stored 4.7 GB of KV remotely, confirming the " +
    "cross-host tier works. On loopback it is not a latency win; its value is capacity and " +
    "cross-host sharing.",
};

export const CONTACT = {
  name: "Rishika Vaish",
  location: "San Jose, CA",
  email: "rishika.vaish@utdallas.edu",
  linkedin: "https://www.linkedin.com/in/rishika-vaish",
  github: "https://github.com/rishika7006",
  repo: "https://github.com/rishika7006/infergate",
};

export const ARCH = {
  stack: ["FastAPI", "vLLM 0.11", "LMCache 0.3.7", "Redis", "Prometheus", "Grafana", "Next.js 14", "Docker"],
  flow: [
    { node: "Client", desc: "OpenAI-compatible request (text + image)" },
    { node: "InferGate gateway", desc: "hashes prefix incl. image bytes → picks warm replica" },
    { node: "vLLM replica fleet", desc: "GPU prefix cache + LMCache CPU KV offload" },
  ],
};
