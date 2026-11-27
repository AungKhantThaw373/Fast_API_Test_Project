"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useEntities, useThreads } from "@/components/wiki/use-wiki";
import {
	ENTITY_TYPE_LABELS,
	activeFilterLabels,
	filtersForApi,
	hasActiveFilters,
	lastSeenLabel,
	oneLineSummary,
	openThreadCount,
	summariseAliases,
	type WikiFilters,
} from "@/components/wiki/wiki-filters";
import type { EntityType, WikiEntity } from "@/lib/api";

const ROW_HEIGHT = 96;
const VIRTUALISE_ABOVE = 100;

export function EntityList({ storyId, filters }: { storyId: string; filters: WikiFilters }) {
	const router = useRouter();
	const entities = useEntities(storyId, filtersForApi(filters));
	const threads = useThreads(storyId);
	const rows = useMemo(() => entities.data ?? [], [entities.data]);
	const [cursor, setCursor] = useState(0);
	const scrollRef = useRef<HTMLDivElement>(null);

	useEffect(() => setCursor(0), [filters.q, filters.type, filters.status]);

	const virtualiser = useVirtualizer({
		count: rows.length,
		getScrollElement: () => scrollRef.current,
		estimateSize: () => ROW_HEIGHT,
		overscan: 8,
	});

	const open = useCallback((entity: WikiEntity) => router.push(`/stories/${storyId}/wiki/${entity.id}`), [router, storyId]);

	useEffect(() => {
		function onKeyDown(event: KeyboardEvent) {
			const target = event.target as HTMLElement | null;
			if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
			if (!rows.length) return;
			if (event.key === "j" || event.key === "ArrowDown") {
				event.preventDefault();
				setCursor((value) => Math.min(value + 1, rows.length - 1));
			} else if (event.key === "k" || event.key === "ArrowUp") {
				event.preventDefault();
				setCursor((value) => Math.max(value - 1, 0));
			} else if (event.key === "Enter") {
				event.preventDefault();
				const entity = rows[cursor];
				if (entity) open(entity);
			}
		}
		document.addEventListener("keydown", onKeyDown);
		return () => document.removeEventListener("keydown", onKeyDown);
	}, [cursor, open, rows]);

	useEffect(() => {
		if (rows.length > VIRTUALISE_ABOVE) virtualiser.scrollToIndex(cursor, { align: "auto" });
	}, [cursor, rows.length, virtualiser]);

	if (entities.isPending) {
		return (
			<div className="wiki-list" aria-busy="true">
				{Array.from({ length: 6 }).map((_, index) => (
					<div className="wiki-row skeleton" key={index}>
						<div className="skeleton-line wide" />
						<div className="skeleton-line" />
					</div>
				))}
			</div>
		);
	}

	if (entities.error) {
		return (
			<div className="wiki-empty" role="alert">
				<h2>The wiki could not load.</h2>
				<p>{entities.error instanceof Error ? entities.error.message : "Try again in a moment."}</p>
				<button className="button button-primary" onClick={() => void entities.refetch()}>
					Try again
				</button>
			</div>
		);
	}

	if (!rows.length) {
		const filtered = hasActiveFilters(filters);
		return (
			<div className={"wiki-empty" + (filtered ? "" : " wiki-empty-rich")}>
				{!filtered && <span className="wiki-empty-emblem" aria-hidden="true">✳</span>}
				<h2>{filtered ? "Nothing matches those filters." : "Your story has not been introduced yet."}</h2>
				<p>
					{filtered
						? `Showing ${activeFilterLabels(filters).join(" · ")}.`
						: "The bible grows from the page: names, places, rules, and the promises between them."}
				</p>
				{!filtered && <div className="wiki-empty-steps"><span><b>01</b>Select a name in the paper.</span><span><b>02</b>Capture what the story knows.</span><span><b>03</b>Accept a fact to make it canon.</span></div>}
				{!filtered && <Link className="button button-primary" href={`/stories/${storyId}`}>Open the paper →</Link>}
			</div>
		);
	}

	return (
		<div className="wiki-list" ref={scrollRef} aria-label="Wiki entries">
			{rows.length > VIRTUALISE_ABOVE ? (
				<div style={{ height: virtualiser.getTotalSize(), position: "relative" }}>
					{virtualiser.getVirtualItems().map((item) => {
						const entity = rows[item.index];
						return (
							<div
								key={entity.id}
								style={{
									position: "absolute",
									top: 0,
									left: 0,
									width: "100%",
									transform: `translateY(${item.start}px)`,
									height: item.size,
								}}
							>
								<EntityRow
									entity={entity}
									threadCount={openThreadCount(entity.id, threads.data ?? [])}
									selected={item.index === cursor}
									onOpen={() => open(entity)}
								/>
							</div>
						);
					})}
				</div>
			) : (
				rows.map((entity, index) => (
					<EntityRow
						key={entity.id}
						entity={entity}
						threadCount={openThreadCount(entity.id, threads.data ?? [])}
						selected={index === cursor}
						onOpen={() => open(entity)}
					/>
				))
			)}
		</div>
	);
}

function EntityRow({
	entity,
	threadCount,
	selected,
	onOpen,
}: {
	entity: WikiEntity;
	threadCount: number;
	selected: boolean;
	onOpen: () => void;
}) {
	const { shown, more } = summariseAliases(entity.aliases);
	return (
		<article className={`wiki-row${selected ? " selected" : ""}${entity.status === "archived" ? " archived" : ""}`}>
			<button className="wiki-row-main" onClick={onOpen}>
				<span className={`wiki-avatar type-${entity.entity_type}`} aria-hidden="true">{entity.name.slice(0, 1)}</span>
				<span className="wiki-row-body">
					<span className="wiki-row-head">
						<strong>{entity.name}</strong>
						<span className="wiki-type-chip">{ENTITY_TYPE_LABELS[entity.entity_type as EntityType] ?? entity.entity_type}</span>
						{entity.status !== "active" && <span className={`wiki-status-chip status-${entity.status}`}>{entity.status}</span>}
					</span>
					<span className="wiki-row-summary">{oneLineSummary(entity)}</span>
					<span className="wiki-row-meta">
						<span>{lastSeenLabel(entity)}</span>
						{threadCount > 0 && <span className="wiki-thread-chip">{threadCount} open {threadCount === 1 ? "thread" : "threads"}</span>}
						{shown.length > 0 && (
							<span className="wiki-aliases">
								{shown.join(" · ")}
								{more > 0 ? ` +${more}` : ""}
							</span>
						)}
					</span>
				</span>
			</button>
			<Link className="text-button subtle wiki-row-open" href={`/stories/${entity.story_id}/wiki/${entity.id}`}>
				Open
			</Link>
		</article>
	);
}
