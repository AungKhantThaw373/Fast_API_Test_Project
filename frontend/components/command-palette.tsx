"use client";

import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { api, type Chapter, type StorySearchHit, type WikiEntity } from "@/lib/api";

interface PaletteAction {
	id: string;
	label: string;
	hint?: string;
	run: () => void;
}

interface CommandPaletteProps {
	storyId: string;
	chapters?: Chapter[];
	/** Studio passes its own chapter switch so the draft is saved first. */
	onChapter?: (chapterId: string) => void;
	/** Jump to a passage without leaving the studio. */
	onSearchHit?: (chapterId: string, line: number) => void;
	onQuietView?: () => void;
	extra?: Array<{ label: string; hint?: string; run: () => void }>;
}

const MAX_RESULTS = 6;
const RECENTS_KEY = "stillroom:command-recents";
const MAX_RECENTS = 4;

function readRecents(): string[] {
	try {
		const parsed: unknown = JSON.parse(window.localStorage.getItem(RECENTS_KEY) ?? "[]");
		return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string").slice(0, MAX_RECENTS) : [];
	} catch {
		return [];
	}
}

/** Cmd/Ctrl+K: go anywhere, find anyone or any passage, start something. */
export function CommandPalette({ storyId, chapters = [], onChapter, onSearchHit, onQuietView, extra = [] }: CommandPaletteProps) {
	const router = useRouter();
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState("");
	const [results, setResults] = useState<WikiEntity[]>([]);
	const [passages, setPassages] = useState<StorySearchHit[]>([]);
	const [searching, setSearching] = useState(false);
	const [recentIds, setRecentIds] = useState<string[]>(() => (typeof window === "undefined" ? [] : readRecents()));
	const openRef = useRef(open);
	const previousFocusRef = useRef<HTMLElement | null>(null);

	useEffect(() => {
		openRef.current = open;
	}, [open]);

	const restoreFocus = () => {
		window.setTimeout(() => previousFocusRef.current?.focus(), 0);
	};

	const openPalette = () => {
		previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		setOpen(true);
	};

	const closePalette = () => {
		setOpen(false);
		setQuery("");
		restoreFocus();
	};

	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent) => {
			if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
				event.preventDefault();
				if (openRef.current) closePalette();
				else openPalette();
			}
		};
		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
		// The listener reads the current open state through a ref; callbacks are not dependencies.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

	useEffect(() => {
		const needle = query.trim();
		if (needle.length < 2) {
			const clear = window.setTimeout(() => {
				setResults([]);
				setPassages([]);
				setSearching(false);
			}, 0);
			return () => window.clearTimeout(clear);
		}
		let alive = true;
		const timer = window.setTimeout(() => {
			setSearching(true);
			void Promise.allSettled([
				api.searchEntities(storyId, needle),
				api.searchStory(storyId, { q: needle, limit: 5 }),
			]).then(([entities, hits]) => {
				if (!alive) return;
				setResults(entities.status === "fulfilled" ? entities.value.slice(0, MAX_RESULTS) : []);
				setPassages(hits.status === "fulfilled" ? hits.value.results.slice(0, 4) : []);
				setSearching(false);
			});
		}, 220);
		return () => {
			alive = false;
			window.clearTimeout(timer);
		};
	}, [query, storyId]);

	const remember = (id: string) => {
		const next = [id, ...recentIds.filter((value) => value !== id)].slice(0, MAX_RECENTS);
		setRecentIds(next);
		try { window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next)); } catch { /* Recents are a convenience, not state. */ }
	};

	const run = (id: string, action: () => void) => {
		remember(id);
		setOpen(false);
		setQuery("");
		action();
		window.setTimeout(() => previousFocusRef.current?.focus(), 0);
	};

	const go = (id: string, path: string) => run(id, () => router.push(path));

	const actions = useMemo<PaletteAction[]>(() => [
		{ id: "nav:studio", label: "Writing studio", hint: "Continue drafting", run: () => router.push(`/stories/${storyId}`) },
		{ id: "nav:wiki", label: "Wiki entries", hint: "Browse canon", run: () => router.push(`/stories/${storyId}/wiki`) },
		{ id: "nav:review", label: "Review inbox", hint: "Decide suggestions", run: () => router.push(`/stories/${storyId}/wiki/review`) },
		{ id: "nav:threads", label: "Threads", hint: "Open plot threads", run: () => router.push(`/stories/${storyId}/wiki/threads`) },
		{ id: "nav:settings", label: "AI and account settings", hint: "Provider and account", run: () => router.push("/settings") },
		{ id: "nav:dashboard", label: "All stories", hint: "Library", run: () => router.push("/dashboard") },
		{ id: "new:entity", label: "New wiki entry", hint: "Character, place, item", run: () => router.push(`/stories/${storyId}/wiki?new=1`) },
		{ id: "new:fact", label: "New fact", hint: "From an entry page", run: () => router.push(`/stories/${storyId}/wiki`) },
		{ id: "new:thread", label: "New thread", hint: "Track a promise", run: () => router.push(`/stories/${storyId}/wiki/threads`) },
		...extra.map((action, index): PaletteAction => ({ id: `extra:${index}`, ...action })),
		...(onQuietView ? [{ id: "view:quiet", label: "Toggle quiet view", hint: "Hide the desk", run: onQuietView }] : []),
	], [extra, onQuietView, router, storyId]);

	const recentActions = useMemo(
		() => recentIds.map((id) => actions.find((action) => action.id === id)).filter((action): action is PaletteAction => Boolean(action)),
		[actions, recentIds],
	);

	const matchedChapters = useMemo(() => {
		const needle = query.trim().toLocaleLowerCase();
		const pool = needle
			? chapters.filter((chapter) =>
					`${chapter.chapter_number} ${chapter.title}`.toLocaleLowerCase().includes(needle),
				)
			: chapters.slice(0, 5);
		return pool.slice(0, MAX_RESULTS);
	}, [chapters, query]);

	const openPassage = (hit: StorySearchHit) => {
		if (onSearchHit) onSearchHit(hit.chapter_id, hit.start_line);
		else router.push(`/stories/${storyId}?chapter=${hit.chapter_id}&line=${hit.start_line}`);
	};

	return (
		<Command.Dialog
			open={open}
			onOpenChange={(next) => {
				if (next) setOpen(true);
				else closePalette();
			}}
			label="Command palette"
			className="command-dialog"
			shouldFilter={false}
		>
			<Command.Input
				value={query}
				onValueChange={setQuery}
				placeholder="Jump to a chapter, search the text, run a check…"
				className="command-input"
				aria-label="Search commands, chapters, entries, and passages"
			/>
			<Command.List className="command-list">
				<Command.Empty className="command-empty">
					{searching ? "Searching the manuscript…" : "Nothing matches yet."}
				</Command.Empty>

				{!query.trim() && recentActions.length > 0 && (
					<Command.Group heading="Recent" className="command-group">
						{recentActions.map((action) => (
							<Command.Item key={`recent:${action.id}`} value={`recent ${action.id} ${action.label}`} onSelect={() => run(action.id, action.run)} className="command-item">
								{action.label}
								{action.hint && <span className="command-hint">{action.hint}</span>}
							</Command.Item>
						))}
					</Command.Group>
				)}

				<Command.Group heading="Actions" className="command-group">
					{actions.map((action) => (
						<Command.Item key={action.id} value={`action ${action.id} ${action.label}`} onSelect={() => run(action.id, action.run)} className="command-item">
							{action.label}
							{action.hint && <span className="command-hint">{action.hint}</span>}
						</Command.Item>
					))}
				</Command.Group>

				{matchedChapters.length > 0 && (
					<Command.Group heading="Chapters" className="command-group">
						{matchedChapters.map((chapter) => (
							<Command.Item
								key={chapter.id}
								value={`chapter ${chapter.chapter_number} ${chapter.title}`}
								onSelect={() =>
									run(`chapter:${chapter.id}`, () => {
										if (onChapter) onChapter(chapter.id);
										else router.push(`/stories/${storyId}?chapter=${chapter.id}`);
									})
								}
								className="command-item"
							>
								<span className="command-chapter-number">{chapter.chapter_number}</span>
								{chapter.title}
								{chapter.arc_id && <span className="command-hint">in an arc</span>}
							</Command.Item>
						))}
					</Command.Group>
				)}

				{results.length > 0 && (
					<Command.Group heading="Entries" className="command-group">
						{results.map((entity) => (
							<Command.Item
								key={entity.id}
								value={`entity ${entity.name}`}
								onSelect={() => go(`entity:${entity.id}`, `/stories/${storyId}/wiki/${entity.id}`)}
								className="command-item"
							>
								{entity.name}
								<span className="command-hint">{entity.entity_type}</span>
							</Command.Item>
						))}
					</Command.Group>
				)}

				{passages.length > 0 && (
					<Command.Group heading="Passages" className="command-group">
						{passages.map((hit) => (
							<Command.Item
								key={hit.chunk_id}
								value={`passage ${hit.chunk_id} ${hit.chapter_title}`}
								onSelect={() => run(`passage:${hit.chunk_id}`, () => openPassage(hit))}
								className="command-item command-passage"
							>
								<span>{hit.quote}</span>
								<span className="command-hint">Ch. {hit.chapter_number} · line {hit.start_line}</span>
							</Command.Item>
						))}
					</Command.Group>
				)}
			</Command.List>
			<footer className="command-footer">
				<span><kbd>↑</kbd><kbd>↓</kbd> move</span>
				<span><kbd>↵</kbd> open</span>
				<span><kbd>esc</kbd> close and return to the editor</span>
				<span className="command-brand">Ctrl/Cmd + K</span>
			</footer>
		</Command.Dialog>
	);
}