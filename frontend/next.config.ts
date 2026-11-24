import type { NextConfig } from "next";

const backendOrigin = (process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

// The backend allows a provider request to run for OPENROUTER_TIMEOUT_SECONDS
// (90s by default). Next's rewrite proxy cuts the response off at 30s unless it
// is raised, which made slow model replies look like failed requests even though
// the scan had already been saved.
const backendProxyTimeoutMs = Number(process.env.BACKEND_PROXY_TIMEOUT_MS ?? "") || 150_000;

const nextConfig: NextConfig = {
	experimental: {
		proxyTimeout: backendProxyTimeoutMs,
	},
	async rewrites() {
		return [{
			source: "/api/py/:path*",
			destination: backendOrigin + "/:path*",
		}];
	},
};

export default nextConfig;
