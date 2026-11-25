"use client";

import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from "@dnd-kit/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useArcs, useChapters, useThreads } from "@/components/wiki/use-wiki";
import { api, type WikiThread } from "@/lib/api";
import { qk } from "@/lib/query-keys";

type ThreadState = WikiThread["state"];

const COLUMNS: { state: ThreadState; label: string; hint: string }[] = [
	{ state: "open", label: "Open", hint: "Promises still waiting" },
	{ state: "touched", label: "Touched", hint: "Mentioned again, not paid off" },
	{ state: "resolved", label: "Resolved", hint: "Paid off in a chapter" },
	{ state: "abandoned", label: "Abandoned", hint: "Deliberately let go" },
];

function ThreadCard({ thread, storyId, overlay = false }: { thread: WikiThread; storyId: string; overlay?: boolean }) {
	return (
		<article className={`thread-board-card state-${thread.state}${overlay ? " is-overlay" : ""}`}>
			<div className="thread-board-card-top">
				<strong>{thread.title}</strong>
			</div>
			{thread.description && <p className="thread-board-description">{thread.description}</p>}
			{thread.linked_entities.length > 0 && (
				<div className="thread-entities">
					{thread.linked_entities.slice(0, 4).map((entity) => (
						<Link key={entity.id} className="alias-chip" href={`/stories/${storyId}/wiki/${entity.id}`}>{entity.name}</Link>
					))}
				</div>
			)}
			<dl className="thread-board-meta">
				{thread.setup_chapter_number != null && (
					<div><dt>Set up</dt><dd><Link href={`/stories/${storyId}?chapter=${thread.setup_chapter_id}`}>Ch. {thread.setup_chapter_number}</Link></dd></div>
				)}
				{thread.last_mention && (
					<div><dt>Last mention</dt><dd><Link href={`/stories/${storyId}?chapter=${thread.last_mention.chapter_id}&line=${thread.last_mention.line}`}>Ch. {thread.last_mention.chapter_number} · L{thread.last_mention.line}</Link></dd></div>
				)}
			</dl>
			{thread.last_mention?.quote && <blockquote className="thread-board-quote">“{thread.last_mention.quote}”</blockquote>}
			{thread.state === "resolved" && thread.payoff_chapter_number != null && (
				<p className="thread-board-payoff">Paid off in Ch. {thread.payoff_chapter_number} · {thread.payoff_chapter_title}</p>
			)}
		</article>
	);
}

function DraggableThread({ thread, storyId }: { thread: WikiThread; storyId: string }) {
	const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: thread.id });
	const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
	return (
		<div ref={setNodeRef} style={style} className={`thread-board-drag${isDragging ? " is-dragging" : ""}`}>
			<button type="button" className="thread-drag-handle" aria-label={`Move ${thread.title}`} {...listeners} {...attributes}>⠿</button>
			<ThreadCard thread={thread} storyId={storyId} />
		</div>
	);
}

function ThreadColumn({ state, label, hint, threads, storyId }: { state: ThreadState; label: string; hint: string; threads: WikiThread[]; storyId: string }) {
	const { setNodeRef, isOver } = useDroppable({ id: state });
	return (
		<section ref={setNodeRef} className={`thread-board-column state-${state}${isOver ? " is-over" : ""}`} aria-label={`${label} threads`}>
			<header>
				<div><h2>{label}</h2><span>{hint}</span></div>
				<strong>{threads.length}</strong>
			</header>
			<div className="thread-board-stack">
				{threads.map((thread) => <DraggableThread key={thread.id} thread={thread} storyId={storyId} />)}
				{threads.length === 0 && <p className="thread-board-empty">Nothing here.</p>}
			</div>
		</section>
	);
}

export function ThreadsPage({ storyId }: { storyId: string }) {
	const queryClient = useQueryClient();
	const threads = useThreads(storyId);
	const chapters = useChapters(storyId);
	const arcs = useArcs(storyId);
	const [activeId, setActiveId] = useState<string | null>(null);
	const [arcFilter, setArcFilter] = useState("");
	const [entityFilter, setEntityFilter] = useState("");
	const [resolving, setResolving] = useState<{ thread: WikiThread; chapterId: string } | null>(null);
	const [creating, setCreating] = useState(false);
	const [draft, setDraft] = useState({ title: "", description: "", chapterId: "" });
	const sensors = useSensors(
		useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
		useSensor(KeyboardSensor),
	);

	const rows = useMemo(() => {
		const all = threads.data ?? [];
		const arcChapterIds = new Set(
			arcFilter
				? (chapters.data ?? []).filter((chapter) => chapter.arc_id === arcFilter).map((chapter) => chapter.id)
				: [],
		);
		return all.filter((thread) => {
			if (entityFilter && !thread.linked_entity_ids.includes(entityFilter)) return false;
			if (arcFilter) {
				const inArc = [thread.setup_chapter_id, thread.payoff_chapter_id, thread.last_mention?.chapter_id]
					.some((chapterId) => Boolean(chapterId && arcChapterIds.has(chapterId)));
				if (!inArc) return false;
			}
			return true;
		});
	}, [arcFilter, chapters.data, entityFilter, threads.data]);

	const entityOptions = useMemo(() => {
		const seen = new Map<string, string>();
		for (const thread of threads.data ?? []) {
			for (const entity of thread.linked_entities) seen.set(entity.id, entity.name);
		}
		return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
	}, [threads.data]);

	const activeThread = threads.data?.find((thread) => thread.id === activeId) ?? null;

	const createThread = useMutation({
		mutationFn: () => api.createThread(storyId, {
			title: draft.title.trim(),
			description: draft.description.trim(),
			setup_chapter_id: draft.chapterId || null,
		}),
		onSuccess: async () => {
			setCreating(false);
			setDraft({ title: "", description: "", chapterId: "" });
			toast.success("Thread added.");
			await queryClient.invalidateQueries({ queryKey: qk.threads(storyId) });
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That thread could not be saved."),
	});

	const setState = useMutation({
		mutationFn: ({ id, state, payoff }: { id: string; state: ThreadState; payoff?: string }) =>
			api.updateThreadEntry(id, { state, ...(payoff ? { payoff_chapter_id: payoff } : {}) }),
		onSuccess: async () => {
			setResolving(null);
			toast.success("Thread moved.");
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: qk.threads(storyId) }),
				queryClient.invalidateQueries({ queryKey: qk.inbox(storyId) }),
			]);
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That thread could not be moved."),
	});

	function onDragStart(event: DragStartEvent) {
		setActiveId(String(event.active.id));
	}

	function onDragEnd(event: DragEndEvent) {
		setActiveId(null);
		const target = event.over?.id as ThreadState | undefined;
		if (!target || !COLUMNS.some((column) => column.state === target)) return;
		const thread = threads.data?.find((row) => row.id === event.active.id);
		if (!thread || thread.state === target) return;
		if (target === "resolved") {
			setResolving({ thread, chapterId: thread.payoff_chapter_id ?? thread.last_mention?.chapter_id ?? "" });
			return;
		}
		setState.mutate({ id: thread.id, state: target });
	}

	return (
		<div className="wiki-page thread-board-page">
			<header className="wiki-page-head">
				<div>
					<div className="eyebrow">WHAT THE STORY OWES</div>
					<h1>Threads</h1>
					<p className="wiki-quiet">Drag a card between columns. Resolving always names the chapter that paid it off.</p>
				</div>
				<button className="quiet-button" onClick={() => setCreating((value) => !value)}>
					{creating ? "Cancel" : "＋ New thread"}
				</button>
			</header>

			{creating && (
				<form
					className="thread-create"
					onSubmit={(event) => {
						event.preventDefault();
						if (draft.title.trim()) createThread.mutate();
					}}
				>
					<label>
						<span>Question or promise</span>
						<input autoFocus value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="Who lit the lantern?" maxLength={300} />
					</label>
					<label>
						<span>What is still unknown</span>
						<textarea rows={2} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} maxLength={20000} />
					</label>
					<label>
						<span>Set up in</span>
						<select value={draft.chapterId} onChange={(event) => setDraft({ ...draft, chapterId: event.target.value })}>
							<option value="">No chapter yet</option>
							{(chapters.data ?? []).map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.chapter_number}. {chapter.title}</option>)}
						</select>
					</label>
					<button className="button button-approve" type="submit" disabled={!draft.title.trim() || createThread.isPending}>Add thread</button>
				</form>
			)}

			<div className="thread-board-filters" aria-label="Thread filters">
				<label>Arc
					<select value={arcFilter} onChange={(event) => setArcFilter(event.target.value)}>
						<option value="">Every arc</option>
						{(arcs.data ?? []).map((arc) => <option key={arc.id} value={arc.id}>{arc.name}</option>)}
					</select>
				</label>
				<label>Entity
					<select value={entityFilter} onChange={(event) => setEntityFilter(event.target.value)}>
						<option value="">Every entity</option>
						{entityOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
					</select>
				</label>
				{(arcFilter || entityFilter) && <button className="text-button subtle" onClick={() => { setArcFilter(""); setEntityFilter(""); }}>Clear filters</button>}
			</div>

			{threads.isPending ? (
				<p className="wiki-quiet">Gathering open questions…</p>
			) : !threads.data?.length ? (
				<div className="wiki-empty">
					<h2>Nothing is dangling.</h2>
					<p>Setups noticed while reading chapters arrive in the review inbox first.</p>
					<Link className="button button-approve" href={`/stories/${storyId}/wiki/review`}>Open the inbox</Link>
				</div>
			) : (
				<DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
					<div className="thread-board">
						{COLUMNS.map((column) => (
							<ThreadColumn
								key={column.state}
								state={column.state}
								label={column.label}
								hint={column.hint}
								storyId={storyId}
								threads={rows.filter((thread) => thread.state === column.state)}
							/>
						))}
					</div>
					<DragOverlay>{activeThread ? <ThreadCard thread={activeThread} storyId={storyId} overlay /> : null}</DragOverlay>
				</DndContext>
			)}

			{resolving && (
				<div className="thread-resolve-backdrop" role="presentation" onClick={() => setResolving(null)}>
					<form
						className="thread-resolve-dialog"
						role="dialog"
						aria-modal="true"
						aria-labelledby="thread-resolve-title"
						onClick={(event) => event.stopPropagation()}
						onSubmit={(event) => {
							event.preventDefault();
							if (resolving.chapterId) setState.mutate({ id: resolving.thread.id, state: "resolved", payoff: resolving.chapterId });
						}}
					>
						<h2 id="thread-resolve-title">Which chapter pays this off?</h2>
						<p>“{resolving.thread.title}” becomes resolved only with a payoff chapter.</p>
						<select autoFocus aria-label="Chapter that pays this off" value={resolving.chapterId} onChange={(event) => setResolving({ ...resolving, chapterId: event.target.value })}>
							<option value="">Choose a chapter</option>
							{(chapters.data ?? []).map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.chapter_number}. {chapter.title}</option>)}
						</select>
						<div className="thread-resolve-actions">
							<button className="button button-approve" type="submit" disabled={!resolving.chapterId || setState.isPending}>Mark resolved</button>
							<button className="text-button subtle" type="button" onClick={() => setResolving(null)}>Cancel</button>
						</div>
					</form>
				</div>
			)}
		</div>
	);
}