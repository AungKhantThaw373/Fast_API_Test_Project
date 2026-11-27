import type { NextConfig } from "next";

const backendOrigin = (process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

// The backend allows a provider request to run for OPENROUTER_TIMEOUT_SECONDS
// (90s by default). Next's rewrite proxy cuts the response off at 30s unless it
// is raised, which made slow model replies look like failed requests even though
// the scan had already been saved.
const backendProxyTimeoutMs = Number(process.env.BACKEND_PROXY_TIMEOUT_MS ?? "") || 150_000;

const securityHeaders = [
	{ key: "X-Content-Type-Options", value: "nosniff" },
	{ key: "X-Frame-Options", value: "DENY" },
	{ key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
	{ key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
	{
		// Report-only until the App Router markup gets a nonce. The policy is
		// already enforced on API responses, where it matters most.
		key: "Content-Security-Policy-Report-Only",
		value: "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
	},
];

const nextConfig: NextConfig = {
	experimental: {
		proxyTimeout: backendProxyTimeoutMs,
	},
	async headers() {
		return [{ source: "/:path*", headers: securityHeaders }];
	},
	async rewrites() {
		return [{
			source: "/api/py/:path*",
			destination: backendOrigin + "/:path*",
		}];
	},
};

export default nextConfig;
