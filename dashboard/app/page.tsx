"use client";

import { useState } from "react";
import { Results } from "@/components/results";
import { Live } from "@/components/live";
import { CONTACT } from "@/lib/results";

type Tab = "results" | "live";

function LogoMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden className="shrink-0">
      <rect x="2" y="2" width="28" height="28" rx="8" stroke="#38bdf8" strokeWidth="2" />
      <path d="M11 9v14M21 9v14" stroke="#34d399" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M11 16h10" stroke="#34d399" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("results");

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <LogoMark />
          <div>
            <div className="text-2xl font-bold tracking-tight text-slate-50">InferGate</div>
            <div className="text-sm text-slate-400">Multimodal Inference Gateway</div>
          </div>
        </div>
        <nav className="flex items-center gap-4 text-sm text-slate-400">
          <a href={CONTACT.github} target="_blank" rel="noreferrer" className="hover:text-white">GitHub</a>
          <a href={CONTACT.linkedin} target="_blank" rel="noreferrer" className="hover:text-white">LinkedIn</a>
          <a href={`mailto:${CONTACT.email}`} className="hover:text-white">Email</a>
        </nav>
      </header>

      <nav className="mb-8 inline-flex rounded-xl border border-edge bg-panel/50 p-1">
        {([
          ["results", "Results"],
          ["live", "Live demo"],
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

      <footer className="mt-12 rounded-2xl border border-edge bg-panel/40 px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-200">Built by {CONTACT.name}</div>
            <div className="text-xs text-slate-500">{CONTACT.location} · Open to collaboration</div>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-400">
            <a href={`mailto:${CONTACT.email}`} className="hover:text-white">{CONTACT.email}</a>
            <a href={CONTACT.linkedin} target="_blank" rel="noreferrer" className="hover:text-white">LinkedIn</a>
            <a href={CONTACT.github} target="_blank" rel="noreferrer" className="hover:text-white">GitHub</a>
          </div>
        </div>
        <div className="mt-4 border-t border-edge pt-3 text-center text-xs text-slate-600">
          Open source · Apache 2.0 · Numbers are measured. See <code>docs/BENCHMARK_REPORT.md</code>.
        </div>
      </footer>
    </main>
  );
}
