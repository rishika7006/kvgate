"use client";

import { useState } from "react";
import { Results } from "@/components/results";
import { Live } from "@/components/live";

type Tab = "results" | "live";

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("results");

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            🚪 InferGate <span className="text-slate-400">— multimodal inference gateway</span>
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            KV-cache offload &amp; prefix-aware routing · benchmarked on Llava-OneVision-7B
          </p>
        </div>
        <a
          href="https://github.com/rishika7006/infergate"
          target="_blank"
          rel="noreferrer"
          className="rounded-lg border border-edge bg-panel/70 px-3 py-2 text-sm text-slate-300 hover:text-white"
        >
          GitHub ↗
        </a>
      </header>

      <nav className="mb-8 inline-flex rounded-xl border border-edge bg-panel/50 p-1">
        {([
          ["results", "📊 Results"],
          ["live", "📡 Live demo"],
        ] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === key ? "bg-sky-500/20 text-sky-300 ring-1 ring-sky-500/30" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "results" ? <Results /> : <Live />}

      <footer className="mt-12 text-center text-xs text-slate-600">
        Open-source · Apache 2.0 · numbers are real measurements — see{" "}
        <code>docs/BENCHMARK_REPORT.md</code>
      </footer>
    </main>
  );
}
