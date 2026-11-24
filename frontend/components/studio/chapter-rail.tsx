"use client";

import { useMemo, useState } from "react";

import type { Chapter, StoryArc } from "@/lib/api";

interface ChapterRailProps {
	chapters: Chapter[];
	arcs: StoryArc[];
	activeId: string | null;
	onSelect: (chapter: Chapter) => void;
	onMove: (chapterId: string, delta: -1 | 1) => void;
	onDelete: (chapter: Chapter) => void;
	onAssign: (chapterId: string, arcId: string | null) => void;
	onCreateArc: (name: string) => Promise<void>;
}

interface Group {
	id: string | null;
	name: string;
	chapters: Chapter[];
}

/** Chapters grouped by arc, with a flat fallback until the writer makes arcs. */
export function ChapterRail({
	chapters,
	arcs,
	activeId,
	onSelect,
	onMove,
	onDelete,
	onAssign,
	onCreateArc,
}: ChapterRailProps) {
	const [collapsed, setCollapsed] = useState<string[]>([]);
	const [addingArc, setAddingArc] = useState(false);
	const [arcName, setArcName] = useState("");

	const groups = useMemo<Group[]>(() => {
		if (!arcs.length) return [{ id: null, name: "Chapters", chapters }];
		const byArc = new Map<string | null, Chapter[]>();
		for (const chapter of chapters) {
			const key = chapter.arc_id ?? null;
			const known = key !== null && arcs.some((arc) => arc.id === key);
			const bucket = known ? key : null;
			byArc.set(bucket, [...(byArc.get(bucket) ?? []), chapter]);
		}
		const ordered: Group[] = arcs.map((arc) => ({
			id: arc.id,
			name: arc.name,
			chapters: byArc.get(arc.id) ?? [],
		}));
		const loose = byArc.get(null) ?? [];
		if (loose.length) ordered.push({ id: null, name: "Not in an arc", chapters: loose });
		return ordered;
	}, [arcs, chapters]);

	const toggle = (id: string) =>
		setCollapsed((current) => (current.includes(id) ? current.filter((value) => value !== id) : [...current, id]));

	const submitArc = async () => {
		const name = arcName.trim();
		if (!name) return;
		await onCreateArc(name);
		setArcName("");
		setAddingArc(false);
	};

	return (
		<nav className="chapter-list" aria-label="Chapters">
			{groups.map((group) => {
				const isCollapsed = group.id ? collapsed.includes(group.id) : false;
				return (
					<section className="arc-group" key={group.id ?? "loose"}>
						{arcs.length > 0 && (
							<header className="arc-group-head">
								<button
									className="arc-group-toggle"
									onClick={() => group.id && toggle(group.id)}
									aria-expanded={group.id ? !isCollapsed : true}
									disabled={!group.id}
								>
									<span className="arc-caret">{isCollapsed ? "▸" : "▾"}</span>
									<span className="arc-name">{group.name}</span>
									<span className="arc-count">{group.chapters.length}</span>
								</button>
							</header>
						)}
						{!isCollapsed &&
							group.chapters.map((chapter) => (
								<div key={chapter.id} className="chapter-nav-block">
									<div className="chapter-nav-row">
									<button
										className={"chapter-nav-item" + (activeId === chapter.id ? " selected" : "")}
										onClick={() => onSelect(chapter)}
									>
										<span className="chapter-nav-number">
											{String(chapter.chapter_number).padStart(2, "0")}
										</span>
										<span className="chapter-nav-copy">
											<strong>{chapter.title}</strong>
											<small>{chapter.word_count.toLocaleString()} words</small>
										</span>
									</button>
									<div className="chapter-row-actions">
										<button
											className="chapter-order-button"
											onClick={() => onMove(chapter.id, -1)}
											disabled={chapter.chapter_number === 1}
											aria-label={`Move ${chapter.title} up`}
											title="Move up"
										>
											↑
										</button>
										<button
											className="chapter-order-button"
											onClick={() => onMove(chapter.id, 1)}
											disabled={chapter.chapter_number === chapters.length}
											aria-label={`Move ${chapter.title} down`}
											title="Move down"
										>
											↓
										</button>
										<button
											className="chapter-delete-button"
											onClick={() => onDelete(chapter)}
											aria-label={`Delete ${chapter.title}`}
											title="Delete chapter"
										>
											×
										</button>
										</div>
									</div>
									{arcs.length > 0 && (
										<div className="chapter-arc-line">
											<label>
												<span className="sr-only">Arc for {chapter.title}</span>
												<select
													className="chapter-arc-select"
													aria-label={`Arc for ${chapter.title}`}
													title="Put this chapter in an arc"
													value={chapter.arc_id ?? ""}
													onChange={(event) => onAssign(chapter.id, event.target.value || null)}
												>
													<option value="">Not in an arc</option>
													{arcs.map((arc) => (
														<option key={arc.id} value={arc.id}>
															{arc.name}
														</option>
													))}
												</select>
											</label>
										</div>
									)}
								</div>
							))}
					</section>
				);
			})}
			{addingArc ? (
				<form
					className="arc-add-form"
					onSubmit={(event) => {
						event.preventDefault();
						void submitArc();
					}}
				>
					<input
						autoFocus
						value={arcName}
						onChange={(event) => setArcName(event.target.value)}
						placeholder="Arc name"
						aria-label="New arc name"
						maxLength={200}
						onKeyDown={(event) => {
							if (event.key === "Escape") setAddingArc(false);
						}}
					/>
					<button className="text-button" type="submit">
						Add
					</button>
				</form>
			) : (
				<button className="arc-add-button" onClick={() => setAddingArc(true)}>
					＋ Arc
				</button>
			)}
		</nav>
	);
}
