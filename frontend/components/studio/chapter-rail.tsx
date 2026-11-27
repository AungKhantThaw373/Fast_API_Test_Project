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

/** Chapters live inside arc folders. Drag a chapter onto a folder to file it. */
export function ChapterRail({ chapters, arcs, activeId, onSelect, onMove, onDelete, onAssign, onCreateArc }: ChapterRailProps) {
	const [collapsed, setCollapsed] = useState<string[]>([]);
	const [addingArc, setAddingArc] = useState(false);
	const [arcName, setArcName] = useState("");
	const [dragging, setDragging] = useState<string | null>(null);
	const [dropTarget, setDropTarget] = useState<string | null>(null);

	const groups = useMemo<Group[]>(() => {
		if (!arcs.length) return [{ id: null, name: "Manuscript", chapters }];
		const byArc = new Map<string | null, Chapter[]>();
		for (const chapter of chapters) {
			const key = chapter.arc_id ?? null;
			const known = key !== null && arcs.some((arc) => arc.id === key);
			const bucket = known ? key : null;
			byArc.set(bucket, [...(byArc.get(bucket) ?? []), chapter]);
		}
		const ordered: Group[] = arcs.map((arc) => ({ id: arc.id, name: arc.name, chapters: byArc.get(arc.id) ?? [] }));
		ordered.push({ id: null, name: "Unsorted", chapters: byArc.get(null) ?? [] });
		return ordered;
	}, [arcs, chapters]);

	const toggle = (id: string) => setCollapsed((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);

	const submitArc = async () => {
		const name = arcName.trim();
		if (!name) return;
		await onCreateArc(name);
		setArcName("");
		setAddingArc(false);
	};

	const dropChapter = (arcId: string | null, chapterId: string | null) => {
		if (chapterId) onAssign(chapterId, arcId);
		setDragging(null);
		setDropTarget(null);
	};

	return (
		<nav className="chapter-list arc-tree" aria-label="Chapters and arcs">
			{groups.map((group, index) => {
				const folderKey = group.id ?? "loose";
				const isCollapsed = group.id ? collapsed.includes(group.id) : false;
				const isDropping = dropTarget === folderKey && dragging !== null;
				return (
					<section
						className={"arc-folder" + (isDropping ? " is-drop-target" : "") + (group.id ? "" : " arc-folder-loose")}
						key={folderKey}
						onDragOver={(event) => {
							event.preventDefault();
							event.dataTransfer.dropEffect = "move";
							setDropTarget(folderKey);
						}}
						onDragLeave={(event) => {
							if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropTarget(null);
						}}
						onDrop={(event) => {
							event.preventDefault();
							dropChapter(group.id, event.dataTransfer.getData("text/plain") || dragging);
						}}
					>
						<header className="arc-folder-head">
							<button
								className="arc-group-toggle"
								onClick={() => group.id && toggle(group.id)}
								aria-expanded={group.id ? !isCollapsed : true}
								disabled={!group.id}
							>
								<span className={"arc-folder-icon" + (isCollapsed ? " is-closed" : "")} aria-hidden="true">{isCollapsed ? "▸" : "▾"}</span>
								<span className="arc-folder-copy">
									<span className="arc-name">{group.name}</span>
									<small>{group.chapters.length} {group.chapters.length === 1 ? "chapter" : "chapters"}</small>
								</span>
								<span className="arc-count">{String(index + 1).padStart(2, "0")}</span>
							</button>
						</header>
						{!isCollapsed && (
							<div className="arc-folder-body">
								{group.chapters.map((chapter) => (
									<div
										key={chapter.id}
										className={"chapter-nav-block" + (dragging === chapter.id ? " is-dragging" : "")}
										draggable
										onDragStart={(event) => {
											setDragging(chapter.id);
											event.dataTransfer.effectAllowed = "move";
											event.dataTransfer.setData("text/plain", chapter.id);
										}}
										onDragEnd={() => { setDragging(null); setDropTarget(null); }}
									>
										<div className="chapter-nav-row">
											<span className="chapter-drag-handle" aria-hidden="true">⠿</span>
											<button
												className={"chapter-nav-item" + (activeId === chapter.id ? " selected" : "")}
												onClick={() => onSelect(chapter)}
											>
												<span className="chapter-nav-number">{String(chapter.chapter_number).padStart(2, "0")}</span>
												<span className="chapter-nav-copy">
													<strong>{chapter.title}</strong>
													<small>{chapter.word_count.toLocaleString()} words</small>
												</span>
											</button>
											<div className="chapter-row-actions">
												<label className="arc-move-control" title="Move to another arc">
													<span aria-hidden="true">⇄</span>
													<select
														className="chapter-arc-select"
														aria-label={`Move ${chapter.title} to an arc`}
														value={chapter.arc_id ?? ""}
														onChange={(event) => onAssign(chapter.id, event.target.value || null)}
													>
														<option value="">Unsorted</option>
														{arcs.map((arc) => <option key={arc.id} value={arc.id}>{arc.name}</option>)}
													</select>
												</label>
												<button className="chapter-order-button" onClick={() => onMove(chapter.id, -1)} disabled={chapter.chapter_number === 1} aria-label={`Move ${chapter.title} up`} title="Move up">↑</button>
												<button className="chapter-order-button" onClick={() => onMove(chapter.id, 1)} disabled={chapter.chapter_number === chapters.length} aria-label={`Move ${chapter.title} down`} title="Move down">↓</button>
												<button className="chapter-delete-button" onClick={() => onDelete(chapter)} aria-label={`Delete ${chapter.title}`} title="Delete chapter">×</button>
											</div>
										</div>
									</div>
								))}
								{group.chapters.length === 0 && (
									<p className="arc-folder-empty">{dragging ? "Drop it in this arc" : "Drag a chapter here"}</p>
								)}
							</div>
						)}
					</section>
				);
			})}
			{addingArc ? (
				<form className="arc-add-form" onSubmit={(event) => { event.preventDefault(); void submitArc(); }}>
					<input autoFocus value={arcName} onChange={(event) => setArcName(event.target.value)} placeholder="Name this arc" aria-label="New arc name" maxLength={200} onKeyDown={(event) => { if (event.key === "Escape") setAddingArc(false); }} />
					<button className="text-button" type="submit">Add</button>
				</form>
			) : (
				<button className="arc-add-button" onClick={() => setAddingArc(true)}>＋ New arc folder</button>
			)}
		</nav>
	);
}
