/** Auth redirects kept outside the API client so pages can reuse them. */

const AUTH_PAGES = ["/login", "/forgot", "/reset"];
const AUTH_ENDPOINTS = new Set(["/token", "/register", "/forgot-password", "/reset-password"]);

let redirectingToLogin = false;

export function isUnauthorized(error: unknown): boolean {
	return (
		typeof error === "object" &&
		error !== null &&
		"status" in error &&
		(error as { status?: unknown }).status === 401
	);
}

export function isAuthEndpoint(path: string): boolean {
	return AUTH_ENDPOINTS.has(path.split("?")[0]);
}

function isAuthPage(pathname: string): boolean {
	return AUTH_PAGES.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

/** Only same-origin absolute paths are valid post-login destinations. */
export function safeNextPath(raw: string | null | undefined): string {
	if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) {
		return "/dashboard";
	}
	const pathname = raw.split("?")[0].split("#")[0];
	return isAuthPage(pathname) ? "/dashboard" : raw;
}

/** Send the writer to login once, preserving the page that lost its session. */
export function redirectToLogin(): void {
	if (typeof window === "undefined" || redirectingToLogin) return;
	const { pathname, search } = window.location;
	if (isAuthPage(pathname)) return;
	redirectingToLogin = true;
	const next = safeNextPath(`${pathname}${search}`);
	window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}