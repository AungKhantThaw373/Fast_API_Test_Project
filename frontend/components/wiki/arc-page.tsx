"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { useArcs, useChapters, useThreads } from "@/components/wiki/use-wiki";
import { api } from "@/lib/api";
import { qk } from "@/lib/query-keys";

/** One arc: what it covers, who is in it, what is still open. */
export function ArcPage({ storyId, arcId }: { storyId: string; arcId: string }) {
	const queryClient = useQueryClient();
	const arcs = useArcs(storyId);
	const chapters = useChapters(storyId);
	const threads = useThreads(storyId);
	const arc = arcs.data?.find((item) => item.id === arcId);

	const arcChapters = (chapters.data ?? []).filter((chapter) => chapter.arc_id === arcId);
	const chapterIds = new Set(arcChapters.map((chapter) => chapter.id));
	const arcThreads = (threads.data ?? []).filter(
		(thread) => thread.setup_chapter_id && chapterIds.has(thread.setup_chapter_id),
	);

	const entities = useQuery({
		queryKey: [...qk.entities(storyId, { arc_id: arcId }), "arc"],
		queryFn: () => api.entities(storyId, { arc_id: arcId, limit: 100 }),
		enabled: Boolean(storyId && arcId),
	});

	const [summary, setSummary] = useState<string | null>(null);
	const [editing, setEditing] = useState(false);

	const save = useMutation({
		mutationFn: (next: string) => api.updateArc(arcId, { summary: next }),
		onSuccess: async () => {
			toast.success("Arc summary saved.");
			setEditing(false);
			await queryClient.invalidateQueries({ queryKey: qk.arcs(storyId) });
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That summary could not be saved."),
	});

	if (arcs.isPending) return <p className="wiki-quiet">Opening the arc…</p>;
	if (!arc) {
		return (
			<div className="wiki-empty">
				<h2>That arc is gone.</h2>
				<Link className="button button-approve" href={`/stories/${storyId}/wiki`}>
					Back to the wiki
				</Link>
			</div>
		);
	}

	return (
		<div className="wiki-page">
			<header className="wiki-page-head">
				<div>
					<div className="eyebrow">
						ARC
						{arc.first_chapter_number !== null && arc.last_chapter_number !== null
							? ` · CHAPTERS ${arc.first_chapter_number}–${arc.last_chapter_number}`
							: ""}
					</div>
					<h1>{arc.name}</h1>
				</div>
				<Link className="quiet-button" href={`/stories/${storyId}/wiki?arc=${arc.id}`}>
					See its entries
				</Link>
			</header>

			<section className="arc-summary" aria-labelledby="arc-summary-heading">
				<div className="wiki-section-head">
					<h2 id="arc-summary-heading">What happens here</h2>
					<button className="text-button subtle" onClick={() => setEditing((value) => !value)}>
						{editing ? "Cancel" : "Edit"}
					</button>
				</div>
				{editing ? (
					<div className="arc-summary-edit">
						<textarea
							rows={5}
							autoFocus
							value={summary ?? arc.summary}
							onChange={(event) => setSummary(event.target.value)}
							placeholder="A few sentences you can reread before diving back in."
							aria-label="Arc summary"
						/>
						<button
							className="button button-approve"
							disabled={save.isPending}
							onClick={() => save.mutate(summary ?? arc.summary)}
						>
							Save summary
						</button>
					</div>
				) : arc.summary ? (
					<p className="arc-summary-text">{arc.summary}</p>
				) : (
					<p className="wiki-quiet">No summary yet. Write what this stretch of the story is for.</p>
				)}
			</section>

			<div className="arc-columns">
				<section aria-labelledby="arc-chapters-heading">
					<div className="wiki-section-head">
						<h2 id="arc-chapters-heading">Chapters</h2>
						<span className="wiki-count">{arcChapters.length}</span>
					</div>
					{arcChapters.length ? (
						<ul className="arc-chapter-list">
							{arcChapters.map((chapter) => (
								<li key={chapter.id}>
									<Link href={`/stories/${storyId}?chapter=${chapter.id}`}>
										<span>{String(chapter.chapter_number).padStart(2, "0")}</span>
										{chapter.title}
									</Link>
									<small>{chapter.word_count.toLocaleString()} words</small>
								</li>
							))}
						</ul>
					) : (
						<p className="wiki-quiet">No chapters in this arc yet.</p>
					)}
				</section>

				<section aria-labelledby="arc-threads-heading">
					<div className="wiki-section-head">
						<h2 id="arc-threads-heading">Open threads</h2>
						<span className="wiki-count">{arcThreads.filter((thread) => thread.state !== "resolved").length}</span>
					</div>
					{arcThreads.length ? (
						<ul className="arc-thread-list">
							{arcThreads.map((thread) => (
								<li key={thread.id} className={thread.state === "resolved" ? "resolved" : ""}>
									<strong>{thread.title}</strong>
									<span>{thread.state === "resolved" ? "Resolved" : "Still open"}</span>
								</li>
							))}
						</ul>
					) : (
						<p className="wiki-quiet">Nothing set up here is still open.</p>
					)}
				</section>
			</div>

			<section aria-labelledby="arc-entities-heading">
				<div className="wiki-section-head">
					<h2 id="arc-entities-heading">Who and what appears</h2>
					<span className="wiki-count">{entities.data?.length ?? 0}</span>
				</div>
				{entities.data?.length ? (
					<ul className="arc-entity-list">
						{entities.data.map((entity) => (
							<li key={entity.id}>
								<Link href={`/stories/${storyId}/wiki/${entity.id}`}>{entity.name}</Link>
								<span>{entity.entity_type.replaceAll("_", " ")}</span>
							</li>
						))}
					</ul>
				) : (
					<p className="wiki-quiet">
						No entries are linked to this arc yet. Entries appear here once they are mentioned in its chapters.
					</p>
				)}
			</section>
		</div>
	);
}
