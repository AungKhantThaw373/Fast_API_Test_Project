import { afterEach, describe, expect, it, vi } from "vitest";

import { isAuthEndpoint, isUnauthorized, safeNextPath } from "../auth-redirect";

afterEach(() => {
	vi.unstubAllGlobals();
	vi.resetModules();
});

describe("auth redirects", () => {
	it("finds the auth endpoints that must not redirect", () => {
		expect(isAuthEndpoint("/token")).toBe(true);
		expect(isAuthEndpoint("/token?next=/settings")).toBe(true);
		expect(isAuthEndpoint("/register")).toBe(true);
		expect(isAuthEndpoint("/reset-password")).toBe(true);
		expect(isAuthEndpoint("/me")).toBe(false);
		expect(isAuthEndpoint("/sessions/revoke-all")).toBe(false);
	});

	it("recognises a 401-shaped error", () => {
		expect(isUnauthorized({ status: 401 })).toBe(true);
		expect(isUnauthorized({ status: 403 })).toBe(false);
		expect(isUnauthorized(new Error("Request failed"))).toBe(false);
		expect(isUnauthorized(null)).toBe(false);
	});

	it("only accepts same-origin page paths", () => {
		expect(safeNextPath("/settings?tab=security")).toBe("/settings?tab=security");
		expect(safeNextPath("/stories/abc/studio")).toBe("/stories/abc/studio");
		expect(safeNextPath("//evil.example/login")).toBe("/dashboard");
		expect(safeNextPath("https://evil.example")).toBe("/dashboard");
		expect(safeNextPath("\\evil.example")).toBe("/dashboard");
		expect(safeNextPath("/login?next=/settings")).toBe("/dashboard");
		expect(safeNextPath("/reset?token=abc")).toBe("/dashboard");
		expect(safeNextPath(null)).toBe("/dashboard");
	});

	it("redirects once and preserves the current path", async () => {
		const assign = vi.fn();
		vi.stubGlobal("window", {
			location: { pathname: "/settings", search: "?tab=security", assign },
		});
		const { redirectToLogin } = await import("../auth-redirect");
		redirectToLogin();
		redirectToLogin();
		expect(assign).toHaveBeenCalledTimes(1);
		expect(assign).toHaveBeenCalledWith("/login?next=%2Fsettings%3Ftab%3Dsecurity");
	});

	it("does not redirect while already on an auth page", async () => {
		const assign = vi.fn();
		vi.stubGlobal("window", {
			location: { pathname: "/login", search: "", assign },
		});
		const { redirectToLogin } = await import("../auth-redirect");
		redirectToLogin();
		expect(assign).not.toHaveBeenCalled();
	});
});