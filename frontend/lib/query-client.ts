"use client";

import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiRequestError } from "./api";
import { isUnauthorized, redirectToLogin } from "./auth-redirect";

export const STALE_TIME_MS = 30_000;
export const GC_TIME_MS = 5 * 60_000;

function handleError(error: unknown) {
	// A dead session should send the writer to the login screen exactly once,
	// even when a page fires several queries in parallel.
	if (isUnauthorized(error)) {
		redirectToLogin();
		return;
	}
	if (!(error instanceof ApiRequestError)) return;
	toast.error(error.message);
}

export function makeQueryClient() {
	return new QueryClient({
		defaultOptions: {
			queries: {
				staleTime: STALE_TIME_MS,
				gcTime: GC_TIME_MS,
				retry: (failureCount, error) => !isUnauthorized(error) && failureCount < 1,
				refetchOnWindowFocus: false,
			},
			mutations: { retry: 0 },
		},
		queryCache: new QueryCache({ onError: handleError }),
		mutationCache: new MutationCache({ onError: handleError }),
	});
}
