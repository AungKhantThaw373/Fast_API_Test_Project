"use client";

import { useDeferredValue, useMemo } from "react";

import { EntityList } from "@/components/wiki/entity-list";
import { parseFilters, activeFilterLabels, hasActiveFilters } from "@/components/wiki/wiki-filters";
import { useDebouncedValue } from "@/lib/use-debounced";

export function EntityListPage({
	storyId,
	searchParams,
}: {
	storyId: string;
	searchParams: Record<string, string | string[] | undefined>;
}) {
	const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
	// Two different delays on purpose: the URL follows every keystroke so the box
	// never lags, the request waits for typing to stop, and the rendered list
	// follows the settled value without blocking the input.
	const settledQuery = useDebouncedValue(filters.q, 200);
	const listFilters = useDeferredValue({ ...filters, q: settledQuery });
	return (
		<div className="wiki-page">
			<header className="wiki-page-head">
				<div>
					<div className="eyebrow">THE STORY, INDEXED</div>
					<h1>Wiki</h1>
				</div>
				{hasActiveFilters(filters) && (
					<p className="wiki-head-filters">Filtered by {activeFilterLabels(filters).join(" · ")}</p>
				)}
			</header>
			<EntityList storyId={storyId} filters={listFilters} />
		</div>
	);
}
