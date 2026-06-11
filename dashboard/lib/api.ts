// Client-side data layer: talks to the KVGate gateway's /admin/stats and
// /metrics endpoints (CORS is open on the gateway) and parses the Prometheus text.

export function gatewayUrl(): string {
  return process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8080";
}

export interface DeploymentStat {
  provider: string;
  upstream_model: string;
  weight: number;
  in_flight: number;
  ewma_latency_ms: number;
  total_requests: number;
  total_failures: number;
  circuit_open: boolean;
  cost_per_1k: number;
}

export interface AdminStats {
  routing_strategy: string;
  cache: { enabled: boolean; backend: string; semantic: boolean; semantic_threshold: number };
  rate_limit: { enabled: boolean; default_rpm: number };
  models: Record<string, DeploymentStat[]>;
}

export interface MetricSample {
  name: string;
  labels: Record<string, string>;
  value: number;
}

export interface ParsedMetrics {
  requestsByStatus: Record<string, number>;
  cache: Record<string, number>; // exact_hit | semantic_hit | miss
  affinity: Record<string, number>; // warm | cold
  tokens: Record<string, number>; // prompt | completion
  totalRequests: number;
}

const LINE = /^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{([^}]*)\})?\s+([0-9.eE+-]+)$/;

export function parsePromText(text: string): MetricSample[] {
  const out: MetricSample[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const m = LINE.exec(line);
    if (!m) continue;
    const labels: Record<string, string> = {};
    if (m[3]) {
      for (const pair of m[3].split(",")) {
        const eq = pair.indexOf("=");
        if (eq === -1) continue;
        const k = pair.slice(0, eq).trim();
        const v = pair.slice(eq + 1).trim().replace(/^"|"$/g, "");
        labels[k] = v;
      }
    }
    out.push({ name: m[1], labels, value: parseFloat(m[4]) });
  }
  return out;
}

export function aggregate(samples: MetricSample[]): ParsedMetrics {
  const requestsByStatus: Record<string, number> = {};
  const cache: Record<string, number> = {};
  const affinity: Record<string, number> = {};
  const tokens: Record<string, number> = {};
  for (const s of samples) {
    if (s.name === "kvgate_requests_total") {
      requestsByStatus[s.labels.status] = (requestsByStatus[s.labels.status] || 0) + s.value;
    } else if (s.name === "kvgate_cache_events_total") {
      cache[s.labels.outcome] = (cache[s.labels.outcome] || 0) + s.value;
    } else if (s.name === "kvgate_routing_affinity_total") {
      affinity[s.labels.outcome] = (affinity[s.labels.outcome] || 0) + s.value;
    } else if (s.name === "kvgate_tokens_total") {
      tokens[s.labels.direction] = (tokens[s.labels.direction] || 0) + s.value;
    }
  }
  const totalRequests = Object.values(requestsByStatus).reduce((a, b) => a + b, 0);
  return { requestsByStatus, cache, affinity, tokens, totalRequests };
}

export async function fetchSnapshot(): Promise<{ stats: AdminStats; metrics: ParsedMetrics }> {
  const base = gatewayUrl();
  const [statsRes, metricsRes] = await Promise.all([
    fetch(`${base}/admin/stats`, { cache: "no-store" }),
    fetch(`${base}/metrics`, { cache: "no-store" }),
  ]);
  if (!statsRes.ok) throw new Error(`/admin/stats -> ${statsRes.status}`);
  const stats = (await statsRes.json()) as AdminStats;
  const metrics = aggregate(parsePromText(await metricsRes.text()));
  return { stats, metrics };
}

export function ratio(part: number, whole: number): number | null {
  return whole > 0 ? part / whole : null;
}

export function pct(x: number | null): string {
  return x === null ? "—" : `${(x * 100).toFixed(1)}%`;
}
