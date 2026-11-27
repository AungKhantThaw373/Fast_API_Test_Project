"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { WikiFormat } from "@/lib/api";

const WikiFormatContext = createContext<WikiFormat | null>(null);

export function WikiFormatProvider({ format, children }: { format: WikiFormat | null; children: ReactNode }) {
	return <WikiFormatContext.Provider value={format}>{children}</WikiFormatContext.Provider>;
}

export function useStoryWikiFormat(): WikiFormat | null {
	return useContext(WikiFormatContext);
}
