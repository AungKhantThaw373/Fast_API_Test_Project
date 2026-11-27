"use client";

import { useMemo, useState } from "react";

import type { Chapter, StoryArc } from "@/lib/api";

type DropPosition = "before" | "after";

interface ChapterRailProps {
	chapters: Chapter[];
	arcs: StoryArc[];
	activeId: string | null;
	onSelect: (chapter: Chapter) => void;
	onReorder: (chapterId: string, targetId: string, position: DropPosition, targetArcId: string | null) => void;
	onDelete: (chapter: Chapter) => void;
	onAssign: (chapterId: string, arcId: string | null) => void;
	onCreateArc: (name: string) => Promise<void>;
	onRenameArc: (arcId: string, name: string) => Promise<void>;
}

interface RailGroup {
	id: string | null;
	name: string;
	chapters: Chapter[];
}

/** Chapters are filed by arc. Drag a chapter onto another chapter to reorder it, or onto an arc to file it. */
export function ChapterRail({ chapters, arcs, activeId, onSelect, onReorder, onDelete, onAssign, onCreateArc, onRenameArc }: ChapterRailProps) {
	const [collapsedIds, setCollapsedIds] = useState<string[]>([]);
	const [addingArc, setAddingArc] = useState(false);
	const [arcName, setArcName] = useState("");
	const [renamingArc, setRenamingArc] = useState<{ id: string; name: string } | null>(null);
	const [draggingId, setDraggingId] = useState<string | null>(null);
	const [groupDropTarget, setGroupDropTarget] = useState<string | null>(null);
	const [chapterDropTarget, setChapterDropTarget] = useState<{ id: string; position: DropPosition } | null>(null);

	const groups = useMemo<RailGroup[]>(() => {
		const byArc = new Map<string | null, Chapter[]>();
		for (const chapter of chapters) {
			const key = chapter.arc_id ?? null;
			const known = key !== null && arcs.some((arc) => arc.id === key);
			const bucket = known ? key : null;
			byArc.set(bucket, [...(byArc.get(bucket) ?? []), chapter]);
		}
		const arcGroups = arcs.map((arc) => ({ id: arc.id, name: arc.name, chapters: byArc.get(arc.id) ?? [] }));
		if (!arcs.length) return [{ id: null, name: "Chapters", chapters }];
		return [...arcGroups, { id: null, name: "Unnamed", chapters: byArc.get(null) ?? [] }];
	}, [arcs, chapters]);

	const toggleGroup = (groupId: string) => {
		setCollapsedIds((current) => current.includes(groupId) ? current.filter((value) => value !== groupId) : [...current, groupId]);
	};

	const clearDragState = () => {
		setDraggingId(null);
		setGroupDropTarget(null);
		setChapterDropTarget(null);
	};

	const submitArc = async () => {
		const name = arcName.trim();
		if (!name) return;
		await onCreateArc(name);
		setArcName("");
		setAddingArc(false);
	};

	const submitArcRename = async () => {
		if (!renamingArc) return;
		const name = renamingArc.name.trim();
		if (!name) return;
		await onRenameArc(renamingArc.id, name);
		setRenamingArc(null);
	};

	const dropOnGroup = (arcId: string | null, chapterId: string | null) => {
		if (chapterId) onAssign(chapterId, arcId);
		clearDragState();
	};

	const dropOnChapter = (target: Chapter, chapterId: string | null) => {
		if (chapterId && chapterId !== target.id) {
			onReorder(chapterId, target.id, chapterDropTarget?.position ?? "before", target.arc_id ?? null);
		}
		clearDragState();
	};

	return (
		<nav className="chapter-list arc-tree" aria-label="Chapters and arcs">
			{groups.map((group) => {
				const groupKey = group.id ?? "unnamed";
				const isCollapsed = group.id ? collapsedIds.includes(group.id) : false;
				const isGroupDropTarget = groupDropTarget === groupKey && draggingId !== null;
				const showLooseHeading = group.id === null && arcs.length > 0;
				return (
					<section
						className={
							group.id
								? "arc-folder" + (isGroupDropTarget ? " is-drop-target" : "")
								: "chapter-group-loose" + (isGroupDropTarget ? " is-drop-target" : "")
						}
						key={groupKey}
						onDragOver={(event) => {
							event.preventDefault();
							event.dataTransfer.dropEffect = "move";
							setGroupDropTarget(groupKey);
							setChapterDropTarget(null);
						}}
						onDragLeave={(event) => {
							if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setGroupDropTarget(null);
						}}
						onDrop={(event) => {
							event.preventDefault();
							dropOnGroup(group.id, event.dataTransfer.getData("text/plain") || draggingId);
						}}
					>
						{group.id && renamingArc?.id === group.id ? (
							<form className="arc-rename-form" onSubmit={(event) => { event.preventDefault(); void submitArcRename(); }}>
								<input
									autoFocus
									value={renamingArc.name}
									onChange={(event) => setRenamingArc({ ...renamingArc, name: event.target.value })}
									onKeyDown={(event) => { if (event.key === "Escape") setRenamingArc(null); }}
									aria-label={`Rename ${group.name} arc`}
									maxLength={200}
								/>
								<button className="text-button" type="submit">Save</button>
								<button className="text-button nav-muted-action" type="button" onClick={() => setRenamingArc(null)}>Cancel</button>
							</form>
						) : group.id ? (
							<div className="arc-folder-head">
								<button
									className="arc-group-toggle"
									onClick={() => toggleGroup(group.id as string)}
									aria-expanded={!isCollapsed}
								>
									<span className={"arc-folder-icon" + (isCollapsed ? " is-closed" : "")} aria-hidden="true">{isCollapsed ? "▸" : "▾"}</span>
									<span className="arc-folder-copy">
										<span className="arc-name">{group.name}</span>
										<small>{group.chapters.length} {group.chapters.length === 1 ? "chapter" : "chapters"}</small>
									</span>
								</button>
								<button className="arc-rename-button" onClick={() => setRenamingArc({ id: group.id as string, name: group.name })} aria-label={`Rename ${group.name} arc`}>Rename</button>
							</div>
						) : showLooseHeading ? (
							<div className="arc-loose-heading">
								<span>Unnamed</span>
								<small>{group.chapters.length} {group.chapters.length === 1 ? "chapter" : "chapters"}</small>
							</div>
						) : null}
						{!isCollapsed && (
							<div className={group.id ? "arc-folder-body" : "chapter-group-body"}>
								{group.chapters.map((chapter) => {
									const chapterDrop = chapterDropTarget?.id === chapter.id ? chapterDropTarget.position : null;
									return (
										<div
											key={chapter.id}
											className={
												"chapter-nav-block"
												+ (draggingId === chapter.id ? " is-dragging" : "")
												+ (chapterDrop === "before" ? " is-drop-before" : "")
												+ (chapterDrop === "after" ? " is-drop-after" : "")
											}
											draggable
											onDragStart={(event) => {
												setDraggingId(chapter.id);
												event.dataTransfer.effectAllowed = "move";
												event.dataTransfer.setData("text/plain", chapter.id);
											}}
											onDragOver={(event) => {
												event.preventDefault();
												event.stopPropagation();
												event.dataTransfer.dropEffect = "move";
												const bounds = event.currentTarget.getBoundingClientRect();
												const position: DropPosition = event.clientY < bounds.top + bounds.height / 2 ? "before" : "after";
												setGroupDropTarget(null);
												setChapterDropTarget({ id: chapter.id, position });
											}}
											onDrop={(event) => {
												event.preventDefault();
												event.stopPropagation();
												dropOnChapter(chapter, event.dataTransfer.getData("text/plain") || draggingId);
											}}
											onDragEnd={clearDragState}
										>
											<div className="chapter-nav-row">
												<span className="chapter-drag-handle" aria-hidden="true" title="Drag to reorder">⠿</span>
												<button
													className={"chapter-nav-item" + (activeId === chapter.id ? " selected" : "")}
													onClick={() => onSelect(chapter)}
													onKeyDown={(event) => {
														if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
														const index = group.chapters.findIndex((item) => item.id === chapter.id);
														const target = group.chapters[event.key === "ArrowUp" ? index - 1 : index + 1];
														if (!target) return;
														event.preventDefault();
														onReorder(chapter.id, target.id, event.key === "ArrowUp" ? "before" : "after", target.arc_id ?? null);
													}}
													aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown"
													title="Drag to reorder, or press Alt+Up/Down"
												>
													<span className="chapter-nav-number">{String(chapter.chapter_number).padStart(2, "0")}</span>
													<span className="chapter-nav-copy">
														<strong>{chapter.title}</strong>
														<small>{chapter.word_count.toLocaleString()} words</small>
													</span>
												</button>
												<div className="chapter-row-actions">
													<button className="chapter-delete-button" onClick={() => onDelete(chapter)} aria-label={`Delete ${chapter.title}`} title="Delete chapter">×</button>
												</div>
											</div>
										</div>
									);
								})}
								{group.chapters.length === 0 && (
									<p className="arc-folder-empty">{draggingId ? (group.id ? "Drop it in this arc" : "Drop it here to remove it from an arc") : (group.id ? "Drag a chapter here" : "Chapters outside an arc appear here")}</p>
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
