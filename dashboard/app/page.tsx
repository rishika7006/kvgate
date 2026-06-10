"use client";

import { useEffect, useRef, useState } from "react";
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

function GitHubIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden className={className}>
      <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.5v-1.8c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17 4.7 18 5 18 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .3.2.6.8.5 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.03-3.04-1.85-3.04-1.86 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.22.79 24 1.77 24h20.45c.98 0 1.78-.78 1.78-1.73V1.73C24 .77 23.2 0 22.22 0z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3.5 7 8.5 6 8.5-6" />
    </svg>
  );
}

function ContactMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  const item = "flex items-center gap-2.5 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-700/40 hover:text-white";
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel/70 px-3 py-2 text-sm text-slate-200 hover:border-slate-500 hover:text-white"
      >
        Contact
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden
          className={`transition-transform ${open ? "rotate-180" : ""}`}>
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-52 overflow-hidden rounded-xl border border-edge bg-panel shadow-xl shadow-black/40">
          <a href={`mailto:${CONTACT.email}`} className={item}>
            <MailIcon /> Email
          </a>
          <a href={CONTACT.linkedin} target="_blank" rel="noreferrer" className={item}>
            <LinkedInIcon /> LinkedIn
          </a>
          <a href={CONTACT.github} target="_blank" rel="noreferrer" className={item}>
            <GitHubIcon /> GitHub profile
          </a>
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("results");

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <LogoMark />
          <div>
            <div className="text-2xl font-bold tracking-tight text-slate-50">InferGate</div>
            <div className="text-sm text-slate-400">Multimodal Inference Gateway</div>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <a
            href={CONTACT.repo}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-lg border border-edge bg-panel/70 px-3 py-2 text-sm text-slate-200 hover:border-slate-500 hover:text-white"
          >
            <GitHubIcon /> Repository
          </a>
          <ContactMenu />
        </div>
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
            <a href={`mailto:${CONTACT.email}`} className="flex items-center gap-1.5 hover:text-white"><MailIcon /> {CONTACT.email}</a>
            <a href={CONTACT.linkedin} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 hover:text-white"><LinkedInIcon /> LinkedIn</a>
            <a href={CONTACT.github} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 hover:text-white"><GitHubIcon /> GitHub</a>
          </div>
        </div>
        <div className="mt-4 border-t border-edge pt-3 text-center text-xs text-slate-600">
          Open source · Apache 2.0 · Numbers are measured. See <code>docs/BENCHMARK_REPORT.md</code>.
        </div>
      </footer>
    </main>
  );
}
