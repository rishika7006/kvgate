# Deploying the InferGate dashboard

The dashboard is a **static Next.js export** (`output: "export"` in `next.config.mjs`) — the
Results tab bakes in the benchmark data, so it needs no backend and hosts anywhere.

## Vercel (recommended — gives a public URL for the demo link)

1. Push the repo to GitHub (done).
2. On <https://vercel.com> → **Add New → Project** → import `rishika7006/infergate`.
3. In project settings set **Root Directory = `dashboard`** (Vercel auto-detects Next.js).
4. Deploy. Every push to `main` redeploys automatically.

No environment variables are required for the Results view. To make the **Live demo** tab
talk to a running gateway, set `NEXT_PUBLIC_GATEWAY_URL` to its URL.

## Any static host (Netlify, GitHub Pages, S3)

```bash
cd dashboard && npm install && npm run build   # emits ./out
# serve ./out with any static file server
```

## Local dev

```bash
cd dashboard && npm install && npm run dev      # http://localhost:3000
```
