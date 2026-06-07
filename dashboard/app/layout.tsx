import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "InferGate Dashboard",
  description: "Live routing, cache, and KV-affinity metrics for the InferGate LLM gateway.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="text-slate-100 antialiased">{children}</body>
    </html>
  );
}
