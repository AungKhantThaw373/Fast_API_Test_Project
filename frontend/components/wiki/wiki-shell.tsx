"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AddEntityDialog } from "@/components/wiki/add-entity-dialog";
import { StoryMobileNav } from "@/components/story-mobile-nav";
import { CommandPalette } from "@/components/command-palette";
import { SavedViews } from "@/components/wiki/saved-views";
import { WikiFormatDialog } from "@/components/wiki/wiki-format-dialog";
import { WikiFormatProvider } from "@/components/wiki/wiki-format-context";
import { useArcs, useCanonCoverage, useChapters, useEntities, useStory, useWikiFormat } from "@/components/wiki/use-wiki";
import { api, type WikiFormat } from "@/lib/api";
import {
	ENTITY_TYPES,
	EMPTY_FILTERS,
	activeFilterLabels,
	entityTypeLabel,
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
	const [formatOpen, setFormatOpen] = useState(false);
	const [filtersOpen, setFiltersOpen] = useState(false);
	const [user, setUser] = useState<string | null>(null);
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
	const wikiFormat = useWikiFormat(storyId);
	const arcs = useArcs(storyId);
	const chapters = useChapters(storyId);
	const coverage = useCanonCoverage(storyId);
	const entities = useEntities(storyId, filtersForApi(filters));
	const rows = useMemo(() => entities.data ?? [], [entities.data]);
	const configuredTypes = useMemo(
		() => wikiFormat.data?.types.map((item) => item.key) ?? ENTITY_TYPES,
		[wikiFormat.data],
	);
	const typeOptions = useMemo(() => {
		const seen = new Set<string>(configuredTypes);
		for (const row of rows) seen.add(row.entity_type);
		if (filters.type) seen.add(filters.type);
		return [...seen].sort((a, b) => {
			const configuredA = configuredTypes.indexOf(a);
			const configuredB = configuredTypes.indexOf(b);
			if (configuredA !== -1 && configuredB !== -1) return configuredA - configuredB;
			if (configuredA !== -1) return -1;
			if (configuredB !== -1) return 1;
			return entityTypeLabel(a, wikiFormat.data).localeCompare(entityTypeLabel(b, wikiFormat.data));
		});
	}, [configuredTypes, filters.type, rows, wikiFormat.data]);
	const railFilterCount = Number(Boolean(filters.type)) + Number(Boolean(filters.status)) + Number(Boolean(filters.arc));
	const currentArc = coverage.data?.arcs.find((arc) => arc.arc_id === coverage.data?.current_arc_id);
	const currentArcIndex = currentArc ? (coverage.data?.arcs.indexOf(currentArc) ?? -1) + 1 : 0;

	useEffect(() => {
		let active = true;
		api.me().then((me) => { if (active) setUser(me.username); }).catch(() => undefined);
		return () => { active = false; };
	}, []);

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
		<AppShell active="wiki" user={user} showBottomNav={false}>
			<div className="wiki-shell">
				<aside className="wiki-rail" aria-label="Wiki filters" data-filters-open={filtersOpen ? "true" : "false"}>
					<Link className="wiki-back-link" href={`/stories/${storyId}`}>
						← Writing desk
					</Link>
					<div className="book-label">STORY WIKI</div>
					<div className="wiki-rail-title-row">
						<div className="rail-story-title" title={story.data?.title ?? ""}>
							{story.data?.title ?? "Loading story…"}
						</div>
						<button
							type="button"
							className="wiki-format-button"
							onClick={() => setFormatOpen(true)}
							disabled={!wikiFormat.data}
							title="Choose entry types, sections, and fields"
						>
							Format
						</button>
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
						Wiki
					</Link>
					<Link className="wiki-nav-link" href={`/stories/${storyId}/wiki/review`} aria-current={pathname.endsWith("/review") ? "page" : undefined}>
						Review
					</Link>
					<Link className="wiki-nav-link" href={`/stories/${storyId}/wiki/threads`} aria-current={pathname.endsWith("/threads") ? "page" : undefined}>
						Threads
					</Link>
					<Link className="wiki-nav-link" href={`/stories/${storyId}`}>
						Write
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
					<button
						type="button"
						className="wiki-filter-toggle"
						aria-expanded={filtersOpen}
						onClick={() => setFiltersOpen((value) => !value)}
					>
						{filtersOpen ? "Hide filters" : "Filters"}
						{railFilterCount ? ` · ${railFilterCount}` : ""}
					</button>
					<label className="wiki-select">
						<span>Type</span>
						<select value={filters.type} onChange={(event) => apply({ ...filters, type: event.target.value })}>
							<option value="">Every type</option>
							{typeOptions.map((type) => (
								<option key={type} value={type}>
									{entityTypeLabel(type, wikiFormat.data)}
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

				<SavedViews filters={filters} onApply={apply} types={wikiFormat.data?.types} />
				<button className="button button-primary button-wide wiki-new-button" onClick={() => setAddOpen(true)}>
					＋ New entry
				</button>
				<p className="wiki-keys-hint">
					<kbd>j</kbd>/<kbd>k</kbd> move · <kbd>Enter</kbd> open · <kbd>/</kbd> search
				</p>
			</aside>

			<WikiFormatProvider format={wikiFormat.data ?? null}>
				<section className="wiki-main">{children}</section>
			</WikiFormatProvider>

			<CommandPalette storyId={storyId} chapters={chapters.data ?? []} />

			{dialogOpen && (
				<AddEntityDialog
					storyId={storyId}
					format={wikiFormat.data}
					initial={{ entityType: configuredTypes[0] ?? "character" }}
					onClose={closeDialog}
					onCreated={(entity) => {
						closeDialog();
						router.push(`/stories/${storyId}/wiki/${entity.id}`);
					}}
				/>
			)}
			{formatOpen && wikiFormat.data && (
				<WikiFormatDialog storyId={storyId} format={wikiFormat.data} onClose={() => setFormatOpen(false)} />
			)}
			</div>
			<StoryMobileNav storyId={storyId} />
		</AppShell>
	);
}

export function WikiShell({ storyId, children }: { storyId: string; children: React.ReactNode }) {
	return (
		<Suspense fallback={<div className="wiki-loading">Opening the wiki…</div>}>
			<WikiShellInner storyId={storyId}>{children}</WikiShellInner>
		</Suspense>
	);
}

export function activeFilterSummary(filters: WikiFilters, format?: WikiFormat | null): string {
	return activeFilterLabels(filters, format).join(" · ");
}
