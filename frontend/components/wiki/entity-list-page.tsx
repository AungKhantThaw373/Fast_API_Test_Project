"use client";

import { useDeferredValue, useMemo } from "react";

import { EntityList } from "@/components/wiki/entity-list";
import { useEntities, useThreads } from "@/components/wiki/use-wiki";
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
	const roster = useEntities(storyId, { limit: 200 });
	const threads = useThreads(storyId);
	const allEntities = roster.data ?? [];
	const people = allEntities.filter((entity) => entity.entity_type === 'character').length;
	const openThreads = (threads.data ?? []).filter((thread) => thread.state !== 'resolved' && thread.state !== 'abandoned').length;
	// Two different delays on purpose: the URL follows every keystroke so the box
	// never lags, the request waits for typing to stop, and the rendered list
	// follows the settled value without blocking the input.
	const settledQuery = useDebouncedValue(filters.q, 200);
	const listFilters = useDeferredValue({ ...filters, q: settledQuery });
	return (
		<div className="wiki-page">
			<header className="wiki-page-head">
				<div className="wiki-title-block">
					<div className="eyebrow">THE STORY, INDEXED</div>
					<h1>Story bible</h1>
					<p>People, places, rules, and the promises between them.</p>
				</div>
				<div className="wiki-stat-strip" aria-label="Wiki at a glance">
					<div className="tone-moss"><strong>{allEntities.length}</strong><span>entries</span></div>
					<div className="tone-rust"><strong>{people}</strong><span>characters</span></div>
					<div className="tone-ochre"><strong>{openThreads}</strong><span>open loops</span></div>
				</div>
				{hasActiveFilters(filters) && (
					<p className="wiki-head-filters">Filtered by {activeFilterLabels(filters).join(" · ")}</p>
				)}
			</header>
			<EntityList storyId={storyId} filters={listFilters} />
		</div>
	);
}
