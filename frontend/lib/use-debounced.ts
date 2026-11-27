"use client";

import { useEffect, useState } from "react";

/**
 * A value that only follows its input after `delayMs` of quiet.
 *
 * Used for the wiki search box: the URL updates on every keystroke so the input
 * never lags, while the query key waits for the typing to stop.
 */
export function useDebouncedValue<T>(value: T, delayMs = 200): T {
	const [settled, setSettled] = useState(value);
	useEffect(() => {
		if (value === settled) return;
		const timer = window.setTimeout(() => setSettled(value), delayMs);
		return () => window.clearTimeout(timer);
	}, [value, settled, delayMs]);
	return settled;
}
