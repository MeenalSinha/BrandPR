// Browser code calls same-origin /api/*; Next proxies those requests to the FastAPI backend.
// BACKEND_URL is read on the server only and is never exposed to the browser bundle.
const backend = process.env.BACKEND_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
