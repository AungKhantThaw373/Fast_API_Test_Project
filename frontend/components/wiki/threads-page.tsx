"use client";

import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent, type DragStartEvent, type KeyboardCoordinateGetter } from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { useArcs, useChapters, useThreads } from "@/components/wiki/use-wiki";
import { api, type WikiThread } from "@/lib/api";
import { useFocusTrap } from "@/lib/focus-trap";
import { qk } from "@/lib/query-keys";

type ThreadState = WikiThread["state"];

const COLUMNS: { state: ThreadState; label: string; hint: string }[] = [
	{ state: "open", label: "Open", hint: "Promises still waiting" },
	{ state: "touched", label: "Touched", hint: "Mentioned again, not paid off" },
	{ state: "resolved", label: "Resolved", hint: "Paid off in a chapter" },
	{ state: "abandoned", label: "Abandoned", hint: "Deliberately let go" },
];

function ThreadCard({ thread, storyId, overlay = false, onEdit }: { thread: WikiThread; storyId: string; overlay?: boolean; onEdit?: (thread: WikiThread) => void }) {
	return (
		<article className={`thread-board-card state-${thread.state}${overlay ? " is-overlay" : ""}`}>
			<div className="thread-board-card-top">
				<strong>{thread.title}</strong>
				{onEdit && <button type="button" className="thread-card-edit" onClick={() => onEdit(thread)} aria-label={`Edit ${thread.title}`}>Edit</button>}
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

function DraggableThread({ thread, storyId, onEdit }: { thread: WikiThread; storyId: string; onEdit: (thread: WikiThread) => void }) {
	const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: thread.id });
	const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
	return (
		<div ref={setNodeRef} style={style} className={`thread-board-drag${isDragging ? " is-dragging" : ""}`}>
			<button type="button" className="thread-drag-handle" aria-label={`Move ${thread.title}`} {...listeners} {...attributes}>⠿</button>
			<ThreadCard thread={thread} storyId={storyId} onEdit={onEdit} />
		</div>
	);
}

function ThreadColumn({ state, label, hint, threads, storyId, onEdit }: { state: ThreadState; label: string; hint: string; threads: WikiThread[]; storyId: string; onEdit: (thread: WikiThread) => void }) {
	const { setNodeRef, isOver } = useDroppable({ id: state });
	return (
		<section ref={setNodeRef} className={`thread-board-column state-${state}${isOver ? " is-over" : ""}`} aria-label={`${label} threads`}>
			<header>
				<div><h2>{label}</h2><span>{hint}</span></div>
				<strong>{threads.length}</strong>
			</header>
			<div className="thread-board-stack">
				{threads.map((thread) => <DraggableThread key={thread.id} thread={thread} storyId={storyId} onEdit={onEdit} />)}
				{threads.length === 0 && <p className="thread-board-empty">Nothing here.</p>}
			</div>
		</section>
	);
}

export function ThreadsPage({ storyId }: { storyId: string }) {
	const queryClient = useQueryClient();
	const confirm = useConfirm();
	const threads = useThreads(storyId);
	const chapters = useChapters(storyId);
	const arcs = useArcs(storyId);
	const [activeId, setActiveId] = useState<string | null>(null);
	const [arcFilter, setArcFilter] = useState("");
	const [entityFilter, setEntityFilter] = useState("");
	const [resolving, setResolving] = useState<{ thread: WikiThread; chapterId: string } | null>(null);
	const resolveRef = useFocusTrap<HTMLFormElement>(Boolean(resolving));
	const [editing, setEditing] = useState<WikiThread | null>(null);
	const [editDraft, setEditDraft] = useState({ title: "", description: "", setupId: "", payoffId: "", linkedIds: [] as string[] });
	const editRef = useFocusTrap<HTMLFormElement>(Boolean(editing));
	const threadsRef = useRef<WikiThread[]>([]);
	useEffect(() => { threadsRef.current = threads.data ?? []; }, [threads.data]);

	// Arrow keys jump one board column at a time instead of nudging 25 px.
	const columnKeyboardCoordinates: KeyboardCoordinateGetter = (event, { context }) => {
		if (event.code !== "ArrowLeft" && event.code !== "ArrowRight") return undefined;
		const activeThread = threadsRef.current.find((row) => row.id === context.active?.id);
		const overState = COLUMNS.some((column) => column.state === context.over?.id) ? context.over?.id as ThreadState : activeThread?.state;
		const index = COLUMNS.findIndex((column) => column.state === overState);
		const next = COLUMNS[index + (event.code === "ArrowRight" ? 1 : -1)];
		if (!next) return undefined;
		const rect = context.droppableRects.get(next.state);
		if (!rect) return undefined;
		// Keyboard coordinates set the collision rect's top-left, so centre the card over the column.
		const width = context.collisionRect?.width ?? 0;
		return { x: rect.left + Math.max(0, (rect.width - width) / 2), y: rect.top + 40 };
	};
	const [creating, setCreating] = useState(false);
	const [draft, setDraft] = useState({ title: "", description: "", chapterId: "" });
	const sensors = useSensors(
		useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
		useSensor(KeyboardSensor, { coordinateGetter: columnKeyboardCoordinates }),
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

	const allEntities = useQuery({
		queryKey: ["thread-editor-entities", storyId] as const,
		queryFn: () => api.entities(storyId, { limit: 200 }),
		enabled: Boolean(editing),
	});

	function openEdit(thread: WikiThread) {
		setEditing(thread);
		setEditDraft({
			title: thread.title,
			description: thread.description,
			setupId: thread.setup_chapter_id ?? "",
			payoffId: thread.payoff_chapter_id ?? "",
			linkedIds: [...thread.linked_entity_ids],
		});
	}

	const updateThread = useMutation({
		mutationFn: () => {
			if (!editing) throw new Error("No thread selected.");
			return api.updateThreadEntry(editing.id, {
				title: editDraft.title.trim(),
				description: editDraft.description.trim(),
				setup_chapter_id: editDraft.setupId || null,
				payoff_chapter_id: editDraft.payoffId || null,
				linked_entity_ids: editDraft.linkedIds,
			});
		},
		onSuccess: async () => {
			setEditing(null);
			toast.success("Thread updated.");
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: qk.threads(storyId) }),
				queryClient.invalidateQueries({ queryKey: qk.inbox(storyId) }),
			]);
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That thread could not be saved."),
	});

	const removeThread = useMutation({
		mutationFn: (id: string) => api.deleteThreadEntry(id),
		onSuccess: async () => {
			setEditing(null);
			toast.success("Thread deleted.");
			await queryClient.invalidateQueries({ queryKey: qk.threads(storyId) });
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That thread could not be deleted."),
	});

	async function confirmDeleteThread() {
		if (!editing) return;
		const ok = await confirm({
			title: "Delete this thread?",
			description: `“${editing.title}” and its setup notes will be removed. The chapters stay untouched.`,
			confirmLabel: "Delete thread",
			destructive: true,
		});
		if (ok) removeThread.mutate(editing.id);
	}

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
								onEdit={openEdit}
								threads={rows.filter((thread) => thread.state === column.state)}
							/>
						))}
					</div>
					<DragOverlay>{activeThread ? <ThreadCard thread={activeThread} storyId={storyId} overlay /> : null}</DragOverlay>
				</DndContext>
			)}

			{editing && (
				<div className="thread-resolve-backdrop" role="presentation" onClick={() => setEditing(null)}>
					<form
						ref={editRef}
						className="thread-resolve-dialog thread-edit-dialog"
						role="dialog"
						aria-modal="true"
						aria-labelledby="thread-edit-title"
						tabIndex={-1}
						onClick={(event) => event.stopPropagation()}
						onKeyDown={(event) => { if (event.key === "Escape") setEditing(null); }}
						onSubmit={(event) => {
							event.preventDefault();
							if (editDraft.title.trim()) updateThread.mutate();
						}}
					>
						<h2 id="thread-edit-title">Edit thread</h2>
						<label>
							<span>Question or promise</span>
							<input data-autofocus value={editDraft.title} onChange={(event) => setEditDraft({ ...editDraft, title: event.target.value })} maxLength={300} />
						</label>
						<label>
							<span>What is still unknown</span>
							<textarea rows={3} value={editDraft.description} onChange={(event) => setEditDraft({ ...editDraft, description: event.target.value })} maxLength={20000} />
						</label>
						<div className="thread-edit-chapters">
							<label>
								<span>Set up in</span>
								<select value={editDraft.setupId} onChange={(event) => setEditDraft({ ...editDraft, setupId: event.target.value })}>
									<option value="">No chapter</option>
									{(chapters.data ?? []).map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.chapter_number}. {chapter.title}</option>)}
								</select>
							</label>
							<label>
								<span>Paid off in</span>
								<select value={editDraft.payoffId} onChange={(event) => setEditDraft({ ...editDraft, payoffId: event.target.value })}>
									<option value="">Not resolved</option>
									{(chapters.data ?? []).map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.chapter_number}. {chapter.title}</option>)}
								</select>
							</label>
						</div>
						<fieldset className="thread-edit-entities">
							<legend>Linked entries</legend>
							{allEntities.isPending ? <small>Loading entries…</small> : null}
							{(allEntities.data ?? []).map((entity) => (
								<label key={entity.id}>
									<input
										type="checkbox"
										checked={editDraft.linkedIds.includes(entity.id)}
										onChange={(event) => setEditDraft({
											...editDraft,
											linkedIds: event.target.checked
												? [...editDraft.linkedIds, entity.id]
												: editDraft.linkedIds.filter((id) => id !== entity.id),
										})}
									/>
									<span>{entity.name}</span>
								</label>
							))}
						</fieldset>
						<div className="thread-resolve-actions">
							<button className="button button-approve" type="submit" disabled={!editDraft.title.trim() || updateThread.isPending}>
								{updateThread.isPending ? "Saving…" : "Save thread"}
							</button>
							<button className="text-button subtle" type="button" onClick={() => setEditing(null)}>Cancel</button>
							<button className="text-button subtle thread-edit-delete" type="button" onClick={() => void confirmDeleteThread()} disabled={removeThread.isPending}>
								{removeThread.isPending ? "Deleting…" : "Delete thread"}
							</button>
						</div>
					</form>
				</div>
			)}

			{resolving && (
				<div className="thread-resolve-backdrop" role="presentation" onClick={() => setResolving(null)}>
					<form
						ref={resolveRef}
						className="thread-resolve-dialog"
						role="dialog"
						aria-modal="true"
						aria-labelledby="thread-resolve-title"
						aria-describedby="thread-resolve-copy"
						tabIndex={-1}
						onClick={(event) => event.stopPropagation()}
						onKeyDown={(event) => { if (event.key === "Escape") setResolving(null); }}
						onSubmit={(event) => {
							event.preventDefault();
							if (resolving.chapterId) setState.mutate({ id: resolving.thread.id, state: "resolved", payoff: resolving.chapterId });
						}}
					>
						<h2 id="thread-resolve-title">Which chapter pays this off?</h2>
						<p id="thread-resolve-copy">“{resolving.thread.title}” becomes resolved only with a payoff chapter.</p>
						<select data-autofocus aria-label="Chapter that pays this off" value={resolving.chapterId} onChange={(event) => setResolving({ ...resolving, chapterId: event.target.value })}>
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