import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KVGate · Multimodal Inference Gateway benchmarks",
  description:
    "Open-source OpenAI-compatible LLM gateway: KV-cache offload (up to 2× lower TTFT) and " +
    "prefix-aware routing (1.84× lower tail latency) benchmarked on Llava-OneVision-7B.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="text-slate-100 antialiased">{children}</body>
    </html>
  );
}
