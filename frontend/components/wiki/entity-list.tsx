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
			<div className="wiki-empty">
				<h2>{filtered ? "Nothing matches those filters." : "Nothing in the wiki yet."}</h2>
				<p>
					{filtered
						? `Showing ${activeFilterLabels(filters).join(" · ")}.`
						: "Scan a chapter or add an entry. Facts you accept will gather here."}
				</p>
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
				<div className="wiki-row-head">
					<strong>{entity.name}</strong>
					<span className="wiki-type-chip">{ENTITY_TYPE_LABELS[entity.entity_type as EntityType] ?? entity.entity_type}</span>
					{entity.status !== "active" && <span className={`wiki-status-chip status-${entity.status}`}>{entity.status}</span>}
				</div>
				<p className="wiki-row-summary">{oneLineSummary(entity)}</p>
				<div className="wiki-row-meta">
					<span>{lastSeenLabel(entity)}</span>
					{threadCount > 0 && <span className="wiki-thread-chip">{threadCount} open {threadCount === 1 ? "thread" : "threads"}</span>}
					{shown.length > 0 && (
						<span className="wiki-aliases">
							{shown.join(" · ")}
							{more > 0 ? ` +${more}` : ""}
						</span>
					)}
				</div>
			</button>
			<Link className="text-button subtle wiki-row-open" href={`/stories/${entity.story_id}/wiki/${entity.id}`}>
				Open
			</Link>
		</article>
	);
}
