"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AddEntityDialog } from "@/components/wiki/add-entity-dialog";
import { CommandPalette } from "@/components/command-palette";
import { SavedViews } from "@/components/wiki/saved-views";
import { useArcs, useCanonCoverage, useChapters, useEntities, useStory } from "@/components/wiki/use-wiki";
import {
	ENTITY_TYPE_LABELS,
	ENTITY_TYPES,
	EMPTY_FILTERS,
	activeFilterLabels,
	filtersForApi,
	hasActiveFilters,
	parseFilters,
	toSearchParams,
	type WikiFilters,
} from "@/components/wiki/wiki-filters";

function WikiShellInner({ storyId, children }: { storyId: string; children: React.ReactNode }) {
	const router = useRouter();
	const pathname = usePathname();
	const searchParams = useSearchParams();
	const filters = useMemo(() => parseFilters(new URLSearchParams(searchParams.toString())), [searchParams]);
	const searchRef = useRef<HTMLInputElement>(null);
	const [addOpen, setAddOpen] = useState(false);
	const [newDismissed, setNewDismissed] = useState(false);
	// ?new=1 is the deep link the command palette uses; closing clears it.
	const newParam = searchParams.get("new");
	const newFromUrl = Boolean(newParam) && !newDismissed;
	const dialogOpen = addOpen || newFromUrl;
	const closeDialog = () => {
		setAddOpen(false);
		if (newFromUrl) {
			setNewDismissed(true);
			router.replace(`${pathname}${toSearchParams(filters)}`, { scroll: false });
		}
	};

	const apply = useCallback(
		(next: WikiFilters) => {
			const query = toSearchParams(next);
			router.replace(`${pathname}${query}`, { scroll: false });
		},
		[pathname, router],
	);

	const story = useStory(storyId);
	const arcs = useArcs(storyId);
	const chapters = useChapters(storyId);
	const coverage = useCanonCoverage(storyId);
	const entities = useEntities(storyId, filtersForApi(filters));
	const rows = entities.data ?? [];
	const currentArc = coverage.data?.arcs.find((arc) => arc.arc_id === coverage.data?.current_arc_id);
	const currentArcIndex = currentArc ? (coverage.data?.arcs.indexOf(currentArc) ?? -1) + 1 : 0;

	// `/` focuses search from anywhere on the page.
	useEffect(() => {
		function onKeyDown(event: KeyboardEvent) {
			const target = event.target as HTMLElement | null;
			const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
			if (event.key === "/" && !typing) {
				event.preventDefault();
				searchRef.current?.focus();
			}
			if (event.key === "Escape" && typing && target === searchRef.current) {
				apply({ ...filters, q: "" });
			}
		}
		document.addEventListener("keydown", onKeyDown);
		return () => document.removeEventListener("keydown", onKeyDown);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [filters]);

	const clearAll = () => {
		apply(EMPTY_FILTERS);
		searchRef.current?.focus();
	};

	return (
		<main className="wiki-shell">
			<aside className="wiki-rail" aria-label="Wiki filters">
				<div className="rail-brand-row">
					<button className="wordmark" onClick={() => void router.push("/dashboard")}>
						<span className="wordmark-icon">s</span>stillroom
					</button>
					<Link className="back-link" href={`/stories/${storyId}`} aria-label="Back to the studio">
						←
					</Link>
				</div>
				<div className="book-label">YOUR STORY</div>
				<div className="rail-story-title" title={story.data?.title ?? ""}>
					{story.data?.title ?? "Loading story…"}
				</div>

				{coverage.data && coverage.data.chapters > 0 ? (
					currentArc ? (
						<Link
							className="wiki-canon-summary"
							href={`/stories/${storyId}/wiki/arcs/${currentArc.arc_id}`}
							aria-label={`Canon coverage: arc ${currentArcIndex} of ${coverage.data.arcs.length}, ${currentArc.extracted_count} of ${currentArc.chapter_count} chapters extracted`}
						>
							<span className="wiki-canon-summary-label">Canon coverage</span>
							<strong>
								Arc {currentArcIndex} of {coverage.data.arcs.length}
							</strong>
							<small>
								{currentArc.extracted_count.toLocaleString()} of{" "}
								{currentArc.chapter_count.toLocaleString()} chapters extracted
							</small>
						</Link>
					) : (
						<div className="wiki-canon-summary">
							<span className="wiki-canon-summary-label">Canon coverage</span>
							<strong>
								{coverage.data.extracted.toLocaleString()} of{" "}
								{coverage.data.chapters.toLocaleString()}
							</strong>
							<small>Assign chapters to an arc to track it here.</small>
						</div>
					)
				) : null}

				<nav className="wiki-rail-links" aria-label="Wiki sections">
					<Link className="wiki-nav-link" href={`/stories/${storyId}/wiki`} aria-current={pathname.endsWith("/wiki") ? "page" : undefined}>
						All entries
					</Link>
					<Link className="wiki-nav-link" href={`/stories/${storyId}/wiki/review`} aria-current={pathname.endsWith("/review") ? "page" : undefined}>
						Review inbox
					</Link>
					<Link className="wiki-nav-link" href={`/stories/${storyId}/wiki/threads`} aria-current={pathname.endsWith("/threads") ? "page" : undefined}>
						Threads
					</Link>
					<Link className="wiki-nav-link" href={`/stories/${storyId}`}>
						Writing studio
					</Link>
				</nav>

				<div className="wiki-filters">
					<label className="wiki-search">
						<span className="sr-only">Search the wiki</span>
						<input
							ref={searchRef}
							type="search"
							value={filters.q}
							onChange={(event) => apply({ ...filters, q: event.target.value })}
							placeholder="Search names, aliases…  /"
							autoComplete="off"
						/>
					</label>
					<label className="wiki-select">
						<span>Type</span>
						<select value={filters.type} onChange={(event) => apply({ ...filters, type: event.target.value })}>
							<option value="">Every type</option>
							{ENTITY_TYPES.map((type) => (
								<option key={type} value={type}>
									{ENTITY_TYPE_LABELS[type]}
								</option>
							))}
						</select>
					</label>
					<label className="wiki-select">
						<span>Status</span>
						<select value={filters.status} onChange={(event) => apply({ ...filters, status: event.target.value })}>
							<option value="">Any status</option>
							<option value="active">Active</option>
							<option value="archived">Archived</option>
						</select>
					</label>
				</div>

				<label className="wiki-select">
					<span>Arc</span>
					<select value={filters.arc} onChange={(event) => apply({ ...filters, arc: event.target.value })} aria-label="Filter by arc">
						<option value="">Every arc</option>
						{(arcs.data ?? []).map((arc) => (
							<option key={arc.id} value={arc.id}>
								{arc.name}
							</option>
						))}
					</select>
				</label>
				<div className="wiki-result-count" role="status" aria-live="polite">
					{entities.isPending ? "Counting…" : `${rows.length} ${rows.length === 1 ? "entry" : "entries"}`}
					{hasActiveFilters(filters) && (
						<button className="text-button subtle" onClick={clearAll}>
							Clear
						</button>
					)}
				</div>

				<SavedViews filters={filters} onApply={apply} />
				<button className="button button-primary button-wide wiki-new-button" onClick={() => setAddOpen(true)}>
					＋ New entry
				</button>
				<p className="wiki-keys-hint">
					<kbd>j</kbd>/<kbd>k</kbd> move · <kbd>Enter</kbd> open · <kbd>/</kbd> search
				</p>
			</aside>

			<section className="wiki-main">{children}</section>

			<CommandPalette storyId={storyId} chapters={chapters.data ?? []} />

			{dialogOpen && (
				<AddEntityDialog
					storyId={storyId}
					onClose={closeDialog}
					onCreated={(entity) => {
						closeDialog();
						router.push(`/stories/${storyId}/wiki/${entity.id}`);
					}}
				/>
			)}
		</main>
	);
}

export function WikiShell({ storyId, children }: { storyId: string; children: React.ReactNode }) {
	return (
		<Suspense fallback={<div className="wiki-loading">Opening the wiki…</div>}>
			<WikiShellInner storyId={storyId}>{children}</WikiShellInner>
		</Suspense>
	);
}

export function activeFilterSummary(filters: WikiFilters): string {
	return activeFilterLabels(filters).join(" · ");
}
