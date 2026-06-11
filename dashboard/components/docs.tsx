import type { ReactNode } from "react";

function Code({ children }: { children: string }) {
  return (
    <pre className="my-3 overflow-x-auto rounded-lg border border-edge bg-ink/60 p-4 text-xs leading-relaxed text-slate-300">
      <code>{children}</code>
    </pre>
  );
}

function K({ children }: { children: ReactNode }) {
  return <code className="rounded bg-slate-700/40 px-1.5 py-0.5 text-[0.85em] text-sky-300">{children}</code>;
}

function Section({ id, title, kicker, children }: { id: string; title: string; kicker?: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6">
      {kicker && <div className="text-xs font-semibold uppercase tracking-wider text-sky-400">{kicker}</div>}
      <h3 className="mb-3 mt-1 text-xl font-semibold text-slate-100">{title}</h3>
      <div className="space-y-3 text-sm leading-relaxed text-slate-400">{children}</div>
    </section>
  );
}

const NAV: { group: string; items: [string, string][] }[] = [
  { group: "Getting started", items: [["intro", "Introduction"], ["quickstart", "Quickstart"], ["config", "Configuration"]] },
  { group: "Guides", items: [["routing", "KV-aware routing"], ["offload", "LMCache KV offload"], ["caching", "Caching"], ["limits", "Rate limits & budgets"], ["stack", "Docker & Grafana"]] },
  { group: "Reference", items: [["api", "API reference"], ["metrics", "Metrics"], ["benchmarks", "Benchmarks"]] },
  { group: "Advanced", items: [["distributed", "Distributed routing"], ["security", "Security"], ["performance", "Performance"]] },
];

export function Docs() {
  return (
    <div className="flex flex-col gap-8 md:flex-row">
      {/* sidebar */}
      <aside className="md:sticky md:top-6 md:h-fit md:w-56 md:shrink-0">
        <nav className="space-y-5">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{g.group}</div>
              <ul className="space-y-1">
                {g.items.map(([id, label]) => (
                  <li key={id}>
                    <a href={`#${id}`} className="block rounded-md px-2 py-1 text-sm text-slate-400 hover:bg-slate-800/40 hover:text-slate-200">
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      {/* content */}
      <div className="min-w-0 flex-1 space-y-10 border-l border-edge pl-0 md:pl-8">
        <Section id="intro" kicker="Getting started" title="Introduction">
          <p>
            KVGate is an open-source, OpenAI-compatible inference gateway that sits in front of a
            fleet of <K>vLLM</K> replicas. Unlike provider-aggregation proxies, it works at the
            <K>KV-cache</K> layer: it routes each request to the replica that already holds its
            prefix (including image bytes) warm, and offloads overflow KV to CPU RAM or Redis via
            LMCache. It also handles the production basics: response caching, rate limiting,
            per-tenant budgets, failover, and Prometheus/Grafana observability.
          </p>
          <p>It runs with zero API keys thanks to a built-in deterministic mock provider.</p>
        </Section>

        <Section id="quickstart" kicker="Getting started" title="Quickstart">
          <p>Clone, install, and start the gateway against the built-in mock providers:</p>
          <Code>{`git clone https://github.com/rishika7006/kvgate.git
cd kvgate
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

kvgate run            # starts on http://localhost:8080`}</Code>
          <p>Send an OpenAI-compatible request:</p>
          <Code>{`curl -s localhost:8080/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"demo","messages":[{"role":"user","content":"Hello"}]}' | jq`}</Code>
          <p>The OpenAI SDK works unchanged — just point <K>base_url</K> at the gateway.</p>
        </Section>

        <Section id="config" kicker="Getting started" title="Configuration">
          <p>
            A <K>model</K> is a logical name clients request; it fans out to one or more
            <K>deployments</K> (provider + upstream model). Point <K>--config</K> at a YAML file:
          </p>
          <Code>{`routing:
  strategy: prefix_kv_aware    # round_robin | latency | least_busy | cost | weighted
models:
  - name: vlm
    deployments:
      - { provider: r1, model: llava-hf/llava-onevision-qwen2-7b-ov-hf }
      - { provider: r2, model: llava-hf/llava-onevision-qwen2-7b-ov-hf }
providers:
  - { name: r1, type: openai_compatible, base_url: http://localhost:8001/v1 }
  - { name: r2, type: openai_compatible, base_url: http://localhost:8002/v1 }`}</Code>
          <p>Validate any config with <K>kvgate validate -c config.yaml</K>. See <K>config/config.example.yaml</K> for the full, commented schema.</p>
        </Section>

        <Section id="routing" kicker="Guides" title="KV-aware routing">
          <p>
            <K>prefix_kv_aware</K> fingerprints each request into block hashes (each image is hashed
            into the key), scores each replica by how long a leading prefix it has served recently,
            and routes to the warmest replica — with a load guard so a shared system prompt can't
            snowball all traffic onto one replica. It infers affinity from traffic the gateway
            already sees, needing no cooperation from the engine.
          </p>
          <Code>{`routing:
  strategy: prefix_kv_aware
  prefix_kv_aware:
    block_size: 16
    image_key: bytes_sha256   # same image collapses, different image diverges
    weight_prefix: 1.0
    weight_load: 0.5
    max_inflight_skew: 2      # load guard: caps imbalance between replicas`}</Code>
          <p>Measured: 1.84× lower TTFT p95 vs round-robin at 98.6% routing-affinity, load balanced.</p>
        </Section>

        <Section id="offload" kicker="Guides" title="LMCache KV offload">
          <p>
            Under GPU memory pressure, vLLM's prefix cache thrashes. LMCache spills overflow KV to
            CPU RAM (or directly to Redis) and recovers it faster than recomputing it. Enable it on
            each vLLM replica:
          </p>
          <Code>{`vllm serve $MODEL --kv-transfer-config \\
  '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'

# lmcache.yaml — CPU tier (fastest offload)
local_cpu: true
max_local_cpu_size: 30
# or Redis tier (cross-host, near-unlimited capacity)
# local_cpu: false
# remote_url: "redis://localhost:6379"`}</Code>
          <p>Measured: up to 2× lower TTFT (5.6× under the tightest cap), +65% throughput.</p>
        </Section>

        <Section id="caching" kicker="Guides" title="Caching">
          <p>
            Identical requests hit an exact cache; reworded prompts hit a semantic cache (cosine
            similarity over embeddings). The Redis backend shares the cache across gateway replicas.
          </p>
          <Code>{`cache:
  enabled: true
  backend: memory        # memory | redis
  ttl_seconds: 3600
  semantic:
    enabled: true
    threshold: 0.95
    embedder: hashing    # hashing (zero-dep) | sentence_transformers | openai`}</Code>
        </Section>

        <Section id="limits" kicker="Guides" title="Rate limits & budgets">
          <p>Token-bucket rate limits and per-tenant spend caps are enforced per API key / tenant:</p>
          <Code>{`ratelimit:
  enabled: true
  default_rpm: 600
  burst: 60
budget:
  enabled: true
  default_usd: 100.0     # per-tenant spend cap per window (null = unlimited)
  window_s: 86400`}</Code>
          <p>When a tenant exceeds its cap, requests are rejected with HTTP 402 until the window resets. Per-key overrides via <K>budget_usd</K> on each API key.</p>
        </Section>

        <Section id="stack" kicker="Guides" title="Docker & Grafana">
          <p>Run the full stack (gateway + Redis + Prometheus + Grafana) with one command:</p>
          <Code>{`cp .env.example .env      # optional: add real API keys
docker compose up --build

# InferGate API : http://localhost:8080  (/docs for Swagger)
# Prometheus     : http://localhost:9090
# Grafana        : http://localhost:3000  (KVGate dashboard pre-loaded)`}</Code>
        </Section>

        <Section id="api" kicker="Reference" title="API reference">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-edge">
              {[
                ["POST /v1/chat/completions", "Chat completions, stream: true|false. OpenAI-compatible."],
                ["GET /v1/models", "List logical models the gateway serves."],
                ["GET /healthz · /readyz", "Liveness / readiness probes."],
                ["GET /metrics", "Prometheus exposition format."],
                ["GET /admin/stats", "Live routing state: per-deployment latency, in-flight, circuit, cost."],
              ].map(([ep, desc]) => (
                <tr key={ep}>
                  <td className="py-2 pr-4 align-top"><K>{ep}</K></td>
                  <td className="py-2 text-slate-400">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>Each response carries a <K>kvgate</K> metadata object: cache status, provider, latencies, and estimated cost.</p>
        </Section>

        <Section id="metrics" kicker="Reference" title="Metrics">
          <p>Prometheus metrics at <K>/metrics</K> include request/latency histograms, cache events, token and cost counters, routing decisions and affinity hits, rate-limit and budget rejections, and per-tenant spend gauges (all prefixed <K>kvgate_</K>).</p>
        </Section>

        <Section id="benchmarks" kicker="Reference" title="Benchmarks">
          <p>
            All numbers are measured on Llava-OneVision-7B on rented A40 GPUs. See the Results tab
            for the charts, or <K>docs/BENCHMARK_REPORT.md</K> in the repo for full methodology and
            honest caveats. Raw data lives under <K>results/</K>.
          </p>
        </Section>

        <Section id="distributed" kicker="Advanced" title="Distributed routing">
          <p>
            The prefix-affinity index can be backed by Redis so routing decisions are shared across
            gateway replicas (set <K>routing.prefix_kv_aware.affinity_backend: redis</K>). Combined
            with LMCache's Redis KV tier, this lets a horizontally-scaled gateway fleet share both
            routing state and KV cache.
          </p>
        </Section>

        <Section id="security" kicker="Advanced" title="Security">
          <p>
            API-key auth resolves a tenant and optional per-key limits from the
            <K>Authorization: Bearer</K> header. Secrets are injected via <K>${"{ENV}"}</K> expansion,
            never stored in the config file. Rate limiting and budgets provide per-tenant isolation.
          </p>
        </Section>

        <Section id="performance" kicker="Advanced" title="Performance">
          <p>
            Gateway overhead is ~1 ms p50 / 1.7 ms p99 per request (measured against a zero-latency
            mock backend) — negligible next to multimodal TTFT of 250–2700 ms. The gateway is
            stateless, so it scales horizontally with more workers/replicas.
          </p>
        </Section>
      </div>
    </div>
  );
}
