"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { ENTITY_TYPE_LABELS, ENTITY_TYPES } from "@/components/wiki/wiki-filters";
import { api, type EntityType } from "@/lib/api";
import { qk } from "@/lib/query-keys";

/**
 * New capitalised names in a chapter that are not in the wiki yet.
 *
 * Zero tokens: this is the alias dictionary doing the work. Accepting one creates
 * the entity, its name alias, and the mention together, which is what makes the
 * name matchable everywhere else.
 */
export function NameCandidatesPanel({
	storyId,
	chapter,
	onOpenEntity,
}: {
	storyId: string;
	chapter: { id: string; chapter_number: number; title: string } | null;
	onOpenEntity?: (entityId: string) => void;
}) {
	const queryClient = useQueryClient();
	const [ignored, setIgnored] = useState<string[]>([]);
	const [renaming, setRenaming] = useState<string | null>(null);
	const [renameValue, setRenameValue] = useState("");
	const [types, setTypes] = useState<Record<string, EntityType>>({});

	const candidates = useQuery({
		queryKey: qk.nameCandidates(chapter?.id ?? ""),
		queryFn: () => api.nameCandidates(storyId, chapter!.id),
		enabled: Boolean(chapter?.id),
	});

	const accept = useMutation({
		mutationFn: (input: { name: string; entityType: EntityType; line?: number; quote?: string }) =>
			api.acceptNameCandidate(storyId, {
				name: input.name,
				entity_type: input.entityType,
				chapter_id: chapter!.id,
				line_start: input.line ?? null,
				quote: input.quote ?? null,
			}),
		onSuccess: async (entity) => {
			toast.success(`${entity.name} added to the wiki.`);
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: qk.nameCandidates(chapter!.id) }),
				queryClient.invalidateQueries({ queryKey: qk.entityList(storyId) }),
				queryClient.invalidateQueries({ queryKey: qk.bible(storyId) }),
			]);
			onOpenEntity?.(entity.id);
		},
	});

	if (!chapter) {
		return <p className="wiki-quiet">Open a chapter to look for new names.</p>;
	}

	const visible = (candidates.data?.candidates ?? []).filter(
		(item) => !ignored.includes(item.name) && !accept.isPending,
	);

	return (
		<section className="name-candidates" aria-labelledby="name-candidates-heading">
			<header className="wiki-section-head">
				<h2 id="name-candidates-heading">New names in chapter {chapter.chapter_number}</h2>
				<button
					className="text-button"
					onClick={() => void candidates.refetch()}
					disabled={candidates.isFetching}
				>
					{candidates.isFetching ? "Looking…" : "Look again"}
				</button>
			</header>
			<p className="pane-hint">
				Capitalised words that are not in the wiki yet. Accepting one creates the entry and makes the
				name matchable everywhere.
			</p>
			{candidates.isPending ? (
				<p className="wiki-quiet">Reading the chapter…</p>
			) : !visible.length ? (
				<p className="wiki-quiet">No new names. Every capitalised name here is already known.</p>
			) : (
				<ul className="candidate-list">
					{visible.map((item) => (
						<li key={item.name} className="candidate-row">
							<div className="candidate-main">
								<strong>{item.name}</strong>
								<span className="candidate-count">
									{item.count}× · line {item.first_line}
								</span>
								<p className="candidate-sample">“{item.sample}”</p>
							</div>
							<div className="candidate-actions">
								{renaming === item.name ? (
									<form
										className="candidate-rename"
										onSubmit={(event) => {
											event.preventDefault();
											if (!renameValue.trim()) return;
											accept.mutate({
												name: renameValue.trim(),
												entityType: types[item.name] ?? "character",
												line: item.first_line,
												quote: item.sample,
											});
											setRenaming(null);
										}}
									>
										<input
											autoFocus
											value={renameValue}
											onChange={(event) => setRenameValue(event.target.value)}
											aria-label="Rename candidate"
											maxLength={200}
										/>
										<button className="text-button" type="submit">
											Save
										</button>
									</form>
								) : (
									<>
										<select
											aria-label={`Type for ${item.name}`}
											value={types[item.name] ?? "character"}
											onChange={(event) =>
												setTypes({ ...types, [item.name]: event.target.value as EntityType })
											}
										>
											{ENTITY_TYPES.map((type) => (
												<option key={type} value={type}>
													{ENTITY_TYPE_LABELS[type]}
												</option>
											))}
										</select>
										<button
											className="button button-approve"
											disabled={accept.isPending}
											onClick={() =>
												accept.mutate({
													name: item.name,
													entityType: types[item.name] ?? "character",
													line: item.first_line,
													quote: item.sample,
												})
											}
										>
											Accept
										</button>
										<button
											className="text-button subtle"
											onClick={() => {
												setRenaming(item.name);
												setRenameValue(item.name);
											}}
										>
											Rename
										</button>
										<button
											className="text-button subtle"
											onClick={() => setIgnored((current) => [...current, item.name])}
										>
											Ignore
										</button>
									</>
								)}
							</div>
						</li>
					))}
				</ul>
			)}
			{accept.error instanceof Error && <p className="form-error">{accept.error.message}</p>}
		</section>
	);
}
