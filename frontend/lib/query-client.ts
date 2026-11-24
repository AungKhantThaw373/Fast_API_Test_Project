"use client";

import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiRequestError } from "./api";

export const STALE_TIME_MS = 30_000;
export const GC_TIME_MS = 5 * 60_000;

let redirectedToLogin = false;

function handleError(error: unknown) {
	if (!(error instanceof ApiRequestError)) return;
	// A dead session should send the writer to the login screen exactly once,
	// even when a page fires several queries in parallel.
	if (error.status === 401) {
		if (typeof window === "undefined" || redirectedToLogin) return;
		if (window.location.pathname.startsWith("/login")) return;
		redirectedToLogin = true;
		const next = `${window.location.pathname}${window.location.search}`;
		window.location.assign(`/login?next=${encodeURIComponent(next)}`);
		return;
	}
	toast.error(error.message);
}

export function makeQueryClient() {
	return new QueryClient({
		defaultOptions: {
			queries: {
				staleTime: STALE_TIME_MS,
				gcTime: GC_TIME_MS,
				retry: 1,
				refetchOnWindowFocus: false,
			},
			mutations: { retry: 0 },
		},
		queryCache: new QueryCache({ onError: handleError }),
		mutationCache: new MutationCache({ onError: handleError }),
	});
}
