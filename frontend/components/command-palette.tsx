"use client";

import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { api, type Chapter, type WikiEntity } from "@/lib/api";

interface CommandPaletteProps {
	storyId: string;
	chapters?: Chapter[];
	/** Studio passes its own chapter switch so the draft is saved first. */
	onChapter?: (chapterId: string) => void;
	onQuietView?: () => void;
	extra?: Array<{ label: string; hint?: string; run: () => void }>;
}

const MAX_RESULTS = 6;

/** Cmd/Ctrl+K: go anywhere, find anyone, start something. */
export function CommandPalette({ storyId, chapters = [], onChapter, onQuietView, extra = [] }: CommandPaletteProps) {
	const router = useRouter();
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState("");
	const [results, setResults] = useState<WikiEntity[]>([]);
	const [searching, setSearching] = useState(false);

	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent) => {
			if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
				event.preventDefault();
				setOpen((value) => !value);
			}
		};
		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, []);

	useEffect(() => {
		const needle = query.trim();
		if (needle.length < 2) {
			const clear = window.setTimeout(() => setResults([]), 0);
			return () => window.clearTimeout(clear);
		}
		let alive = true;
		const timer = window.setTimeout(() => {
			setSearching(true);
			api.searchEntities(storyId, needle)
				.then((entities) => {
					if (alive) setResults(entities.slice(0, MAX_RESULTS));
				})
				.catch(() => {
					if (alive) setResults([]);
				})
				.finally(() => {
					if (alive) setSearching(false);
				});
		}, 200);
		return () => {
			alive = false;
			window.clearTimeout(timer);
		};
	}, [query, storyId]);

	const run = (action: () => void) => {
		setOpen(false);
		setQuery("");
		action();
	};

	const go = (path: string) => run(() => router.push(path));

	const matchedChapters = useMemo(() => {
		const needle = query.trim().toLocaleLowerCase();
		const pool = needle
			? chapters.filter((chapter) =>
					`${chapter.chapter_number} ${chapter.title}`.toLocaleLowerCase().includes(needle),
				)
			: chapters.slice(0, 5);
		return pool.slice(0, MAX_RESULTS);
	}, [chapters, query]);

	return (
		<Command.Dialog
			open={open}
			onOpenChange={(next) => {
				setOpen(next);
				if (!next) setQuery("");
			}}
			label="Command palette"
			className="command-dialog"
			shouldFilter={false}
		>
			<Command.Input
				value={query}
				onValueChange={setQuery}
				placeholder="Search entries, jump to a chapter, start something…"
				className="command-input"
			/>
			<Command.List className="command-list">
				<Command.Empty className="command-empty">
					{searching ? "Searching…" : "Nothing matches yet."}
				</Command.Empty>

				<Command.Group heading="Go" className="command-group">
					<Command.Item onSelect={() => go(`/stories/${storyId}`)} className="command-item">
						Writing studio
					</Command.Item>
					<Command.Item onSelect={() => go(`/stories/${storyId}/wiki`)} className="command-item">
						Wiki entries
					</Command.Item>
					<Command.Item onSelect={() => go(`/stories/${storyId}/wiki/review`)} className="command-item">
						Review inbox
					</Command.Item>
					<Command.Item onSelect={() => go(`/stories/${storyId}/wiki/threads`)} className="command-item">
						Threads
					</Command.Item>
					<Command.Item onSelect={() => go("/settings")} className="command-item">
						AI and account settings
					</Command.Item>
					<Command.Item onSelect={() => go("/dashboard")} className="command-item">
						All stories
					</Command.Item>
				</Command.Group>

				{matchedChapters.length > 0 && (
					<Command.Group heading="Chapters" className="command-group">
						{matchedChapters.map((chapter) => (
							<Command.Item
								key={chapter.id}
								value={`chapter ${chapter.chapter_number} ${chapter.title}`}
								onSelect={() =>
									run(() => {
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
								onSelect={() => go(`/stories/${storyId}/wiki/${entity.id}`)}
								className="command-item"
							>
								{entity.name}
								<span className="command-hint">{entity.entity_type}</span>
							</Command.Item>
						))}
					</Command.Group>
				)}

				<Command.Group heading="Start" className="command-group">
					<Command.Item onSelect={() => go(`/stories/${storyId}/wiki?new=1`)} className="command-item">
						New wiki entry
					</Command.Item>
					{onQuietView && (
						<Command.Item onSelect={() => run(onQuietView)} className="command-item">
							Toggle quiet view
						</Command.Item>
					)}
					{extra.map((action) => (
						<Command.Item key={action.label} onSelect={() => run(action.run)} className="command-item">
							{action.label}
							{action.hint && <span className="command-hint">{action.hint}</span>}
						</Command.Item>
					))}
				</Command.Group>
			</Command.List>
			<footer className="command-footer">
				<span>
					<kbd>↑</kbd>
					<kbd>↓</kbd> move
				</span>
				<span>
					<kbd>↵</kbd> open
				</span>
				<span>
					<kbd>esc</kbd> close
				</span>
				<span className="command-brand">Ctrl/Cmd + K</span>
			</footer>
		</Command.Dialog>
	);
}
