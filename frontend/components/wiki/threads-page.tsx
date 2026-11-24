"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useChapters, useThreads } from "@/components/wiki/use-wiki";
import { capitalise } from "@/components/wiki/wiki-filters";
import { api, type WikiThread } from "@/lib/api";
import { qk } from "@/lib/query-keys";

type StateFilter = "open" | "all" | "resolved";

/** What is unresolved? Threads are the story's own promises, not AI guesses. */
export function ThreadsPage({ storyId }: { storyId: string }) {
	const queryClient = useQueryClient();
	const threads = useThreads(storyId);
	const chapters = useChapters(storyId);
	const [filter, setFilter] = useState<StateFilter>("open");
	// Resolving a thread means naming the chapter that paid it off.
	const [resolving, setResolving] = useState<{ id: string; chapterId: string } | null>(null);
	const [creating, setCreating] = useState(false);
	const [draft, setDraft] = useState({ title: "", description: "", chapterId: "" });

	const rows = useMemo(() => {
		const all = threads.data ?? [];
		if (filter === "all") return all;
		if (filter === "resolved") return all.filter((thread) => thread.state === "resolved" || thread.state === "abandoned");
		return all.filter((thread) => thread.state === "open" || thread.state === "touched");
	}, [threads.data, filter]);

	const counts = useMemo(() => {
		const all = threads.data ?? [];
		return {
			open: all.filter((thread) => thread.state === "open" || thread.state === "touched").length,
			resolved: all.filter((thread) => thread.state === "resolved" || thread.state === "abandoned").length,
			all: all.length,
		};
	}, [threads.data]);

	const createThread = useMutation({
		mutationFn: () =>
			api.createThread(storyId, {
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
		mutationFn: ({ id, state, payoff }: { id: string; state: WikiThread["state"]; payoff?: string }) =>
			api.updateThreadEntry(id, { state, ...(payoff ? { payoff_chapter_id: payoff } : {}) }),
		onSuccess: async () => {
			setResolving(null);
			toast.success("Thread updated.");
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: qk.threads(storyId) }),
				queryClient.invalidateQueries({ queryKey: qk.inbox(storyId) }),
			]);
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That thread could not be changed."),
	});

	return (
		<div className="wiki-page">
			<header className="wiki-page-head">
				<div>
					<div className="eyebrow">WHAT THE STORY OWES</div>
					<h1>Threads</h1>
				</div>
				<button className="quiet-button" onClick={() => setCreating((value) => !value)}>
					{creating ? "Cancel" : "＋ New thread"}
				</button>
				<div className="inbox-tabs" role="tablist" aria-label="Thread state">
					{(["open", "resolved", "all"] as StateFilter[]).map((value) => (
						<button
							key={value}
							role="tab"
							aria-selected={filter === value}
							className={filter === value ? "active" : ""}
							onClick={() => setFilter(value)}
						>
							{capitalise(value)}
							<span>{counts[value]}</span>
						</button>
					))}
				</div>
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
						<input
							autoFocus
							value={draft.title}
							onChange={(event) => setDraft({ ...draft, title: event.target.value })}
							placeholder="Who lit the lantern?"
							maxLength={300}
						/>
					</label>
					<label>
						<span>What is still unknown</span>
						<textarea
							rows={2}
							value={draft.description}
							onChange={(event) => setDraft({ ...draft, description: event.target.value })}
							maxLength={20000}
						/>
					</label>
					<label>
						<span>Set up in</span>
						<select value={draft.chapterId} onChange={(event) => setDraft({ ...draft, chapterId: event.target.value })}>
							<option value="">No chapter yet</option>
							{(chapters.data ?? []).map((chapter) => (
								<option key={chapter.id} value={chapter.id}>
									{chapter.chapter_number}. {chapter.title}
								</option>
							))}
						</select>
					</label>
					<button className="button button-approve" type="submit" disabled={!draft.title.trim() || createThread.isPending}>
						Add thread
					</button>
				</form>
			)}

			{threads.isPending ? (
				<p className="wiki-quiet">Gathering open questions…</p>
			) : !rows.length ? (
				<div className="wiki-empty">
					<h2>{filter === "open" ? "Nothing is dangling." : "Nothing here yet."}</h2>
					<p>Setups noticed while reading chapters arrive in the review inbox first.</p>
					<Link className="button button-approve" href={`/stories/${storyId}/wiki/review`}>
						Open the inbox
					</Link>
				</div>
			) : (
				<ul className="thread-list">
					{rows.map((thread) => (
						<li key={thread.id} className={`thread-card state-${thread.state}`}>
							<div className="thread-status">{thread.state === "resolved" ? "Resolved" : thread.state === "abandoned" ? "Abandoned" : thread.state === "touched" ? "Touched" : "Still open"}</div>
							<h2>{thread.title}</h2>
							<p>{thread.description}</p>
							{thread.setup_quote && <blockquote>“{thread.setup_quote}”</blockquote>}
							{thread.setup_chapter_id && (
								<Link className="provenance-chip" href={`/stories/${storyId}?chapter=${thread.setup_chapter_id}`}>
									Setup chapter
								</Link>
							)}
							{thread.linked_entity_ids.length > 0 && (
								<div className="thread-entities">
									{thread.linked_entity_ids.slice(0, 6).map((entityId) => (
										<Link key={entityId} className="alias-chip" href={`/stories/${storyId}/wiki/${entityId}`}>
											Entry
										</Link>
									))}
								</div>
							)}
							<div className="inbox-item-actions">
								{thread.state !== "resolved" ? (
									resolving?.id === thread.id ? (
										<span className="thread-resolve-form">
											<select
												aria-label="Chapter that pays this off"
												value={resolving.chapterId}
												onChange={(event) => setResolving({ id: thread.id, chapterId: event.target.value })}
											>
												<option value="">Which chapter pays it off?</option>
												{(chapters.data ?? []).map((chapter) => (
													<option key={chapter.id} value={chapter.id}>
														{chapter.chapter_number}. {chapter.title}
													</option>
												))}
											</select>
											<button
												className="button button-approve"
												disabled={!resolving.chapterId || setState.isPending}
												onClick={() =>
													setState.mutate({ id: thread.id, state: "resolved", payoff: resolving.chapterId })
												}
											>
												Save
											</button>
											<button className="text-button subtle" onClick={() => setResolving(null)}>
												Cancel
											</button>
										</span>
									) : (
										<button
											className="button button-approve"
											onClick={() => setResolving({ id: thread.id, chapterId: thread.payoff_chapter_id ?? "" })}
										>
											Mark resolved
										</button>
									)
								) : (
									<button className="quiet-button" onClick={() => setState.mutate({ id: thread.id, state: "open" })}>
										Reopen
									</button>
								)}
								{thread.state !== "abandoned" && (
									<button
										className="text-button subtle"
										onClick={() => setState.mutate({ id: thread.id, state: "abandoned" })}
									>
										Let it go
									</button>
								)}
								{thread.payoff_chapter_id && (
									<Link className="text-button" href={`/stories/${storyId}?chapter=${thread.payoff_chapter_id}`}>
										Payoff
									</Link>
								)}
							</div>
						</li>
					))}
				</ul>
			)}
		</div>
	);
}
