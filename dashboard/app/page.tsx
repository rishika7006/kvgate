"use client";

import { useEffect, useRef, useState } from "react";
import { Results } from "@/components/results";
import { Live } from "@/components/live";
import { Docs } from "@/components/docs";
import { CONTACT } from "@/lib/results";

type Tab = "results" | "docs" | "live";

function LogoMark() {
  // Distributed cache mesh: a hexagon with a warm central node linked to peer nodes.
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden className="shrink-0">
      <path d="M16 3.5l10.4 6v13l-10.4 6-10.4-6v-13z" stroke="#38bdf8" strokeWidth="2" fill="none" strokeLinejoin="round" />
      <path d="M16 16l-5-3M16 16l5-3M16 16v6" stroke="#64748b" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="16" cy="16" r="2.5" fill="#34d399" />
      <circle cx="11" cy="13" r="1.7" fill="#38bdf8" />
      <circle cx="21" cy="13" r="1.7" fill="#38bdf8" />
      <circle cx="16" cy="22" r="1.7" fill="#38bdf8" />
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

const TABS: [Tab, string][] = [
  ["results", "Results"],
  ["docs", "Docs"],
  ["live", "Live demo"],
];

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.slice(1) as Tab;
      if (TABS.some(([k]) => k === h)) return h;
    }
    return "results";
  });

  function selectTab(t: Tab) {
    setTab(t);
    if (typeof window !== "undefined") window.history.replaceState(null, "", `#${t}`);
  }

  useEffect(() => {
    function onHash() {
      const h = window.location.hash.slice(1) as Tab;
      if (TABS.some(([k]) => k === h)) {
        setTab(h);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <LogoMark />
          <div>
            <div className="text-2xl font-bold tracking-tight text-slate-50">KVGate</div>
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
        {TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => selectTab(key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === key ? "bg-sky-500/20 text-sky-300 ring-1 ring-sky-500/30" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "results" ? <Results /> : tab === "docs" ? <Docs /> : <Live />}

      {/* bottom bookend: closing CTA + contact */}
      <footer className="mt-12">
        <div className="rounded-3xl border border-edge bg-gradient-to-br from-panel/80 to-panel/40 px-8 py-10 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-50">Let&apos;s build fast inference together</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-slate-400">
            KVGate is open source and built by {CONTACT.name}, a new-grad software/ML engineer in {CONTACT.location}.
            Open to roles and collaboration.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <a href={CONTACT.repo} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-lg bg-sky-500/20 px-4 py-2 text-sm font-medium text-sky-300 ring-1 ring-sky-500/30 hover:bg-sky-500/30">
              <GitHubIcon /> View on GitHub
            </a>
            <a href={CONTACT.linkedin} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-lg border border-edge bg-panel/70 px-4 py-2 text-sm text-slate-200 hover:text-white">
              <LinkedInIcon /> LinkedIn
            </a>
            <a href={`mailto:${CONTACT.email}`} className="flex items-center gap-2 rounded-lg border border-edge bg-panel/70 px-4 py-2 text-sm text-slate-200 hover:text-white">
              <MailIcon /> {CONTACT.email}
            </a>
          </div>
        </div>
        <div className="mt-5 text-center text-xs text-slate-600">
          Open source · Apache 2.0 · Numbers are measured. See <code>docs/BENCHMARK_REPORT.md</code>.
        </div>
      </footer>
    </main>
  );
}
