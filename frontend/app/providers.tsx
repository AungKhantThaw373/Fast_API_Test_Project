"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "sonner";

import { makeQueryClient } from "@/lib/query-client";

export function Providers({ children }: { children: React.ReactNode }) {
	// One client per browser session, created lazily so the server render and the
	// first client render agree.
	const [queryClient] = useState(makeQueryClient);
	return (
		<QueryClientProvider client={queryClient}>
			{children}
			<Toaster position="bottom-right" richColors closeButton />
		</QueryClientProvider>
	);
}
