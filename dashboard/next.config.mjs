/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Fully static export: the Results tab bakes in benchmark data, so the whole app is
  // client-rendered and needs no server runtime — deployable to Vercel (or any static host).
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
