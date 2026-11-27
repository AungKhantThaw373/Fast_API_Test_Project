"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { FactDialog, EMPTY_FACT, draftFromFact, type FactDraft } from "@/components/wiki/fact-dialog";
import { FactSection } from "@/components/wiki/fact-section";
import { MergeDialog } from "@/components/wiki/merge-dialog";
import {
	useEntities,
	useEntity,
	useEntityAppearances,
	useEntityFacts,
	useEntityRelationships,
	useStory,
	useThreads,
} from "@/components/wiki/use-wiki";
import { ENTITY_TYPE_LABELS, ENTITY_TYPES, capitalise, entityTypeLabel, normalizeEntityType } from "@/components/wiki/wiki-filters";
import { api, type EntityFact, type EntityRelationship } from "@/lib/api";
import { qk } from "@/lib/query-keys";

export function EntityDetail({ storyId, entityId }: { storyId: string; entityId: string }) {
	const router = useRouter();
	const confirm = useConfirm();
	const queryClient = useQueryClient();
	const entity = useEntity(entityId);
	const story = useStory(storyId);
	const facts = useEntityAppearances(entityId);
	const factRows = useEntityFacts(entityId);
	const relationships = useEntityRelationships(entityId);
	const threads = useThreads(storyId);
	const allEntities = useEntities(storyId, {});

	const [aliasDraft, setAliasDraft] = useState("");
	const [addingAlias, setAddingAlias] = useState(false);
	const [summaryDraft, setSummaryDraft] = useState<string | null>(null);
	const [editing, setEditing] = useState(false);
	const [factDialog, setFactDialog] = useState<{ fact: EntityFact | null } | null>(null);
	const [mergeOpen, setMergeOpen] = useState(false);
	const [relType, setRelType] = useState("");
	const [relTarget, setRelTarget] = useState("");
	const [relDescription, setRelDescription] = useState("");
	const [relOpen, setRelOpen] = useState(false);
	const [relEdit, setRelEdit] = useState<{ id: string; type: string; description: string } | null>(null);

	const linkedThreads = useMemo(() => {
		const list = threads.data ?? [];
		return list.filter((thread) => thread.linked_entity_ids.includes(entityId));
	}, [threads.data, entityId]);

	const appearanceChapters = useMemo(() => {
		const chapters = new Map<string, { chapter_id: string; chapter_number: number; chapter_title: string }>();
		for (const appearance of facts.data ?? []) {
			if (!chapters.has(appearance.chapter_id)) chapters.set(appearance.chapter_id, {
				chapter_id: appearance.chapter_id,
				chapter_number: appearance.chapter_number,
				chapter_title: appearance.chapter_title,
			});
		}
		return [...chapters.values()].sort((a, b) => a.chapter_number - b.chapter_number);
	}, [facts.data]);

	const nameById = useMemo(() => {
		const names = new Map<string, string>();
		if (entity.data) names.set(entity.data.id, entity.data.name);
		for (const row of allEntities.data ?? []) names.set(row.id, row.name);
		return names;
	}, [entity.data, allEntities.data]);

	const invalidateEntity = async (id: string) => {
		await Promise.all([
			queryClient.invalidateQueries({ queryKey: qk.entity(id) }),
			queryClient.invalidateQueries({ queryKey: qk.entityFacts(id) }),
			queryClient.invalidateQueries({ queryKey: qk.entityList(storyId) }),
			queryClient.invalidateQueries({ queryKey: qk.inbox(storyId) }),
		]);
	};

	const saveSummary = useMutation({
		mutationFn: (summary: string) => api.updateEntity(entityId, { summary }),
		onSuccess: async () => {
			toast.success("Summary saved.");
			setSummaryDraft(null);
			await invalidateEntity(entityId);
		},
	});

	const addAlias = useMutation({
		mutationFn: (alias: string) => api.addEntityAlias(entityId, alias),
		onSuccess: async () => {
			setAliasDraft("");
			setAddingAlias(false);
			await invalidateEntity(entityId);
		},
	});

	const removeAlias = useMutation({
		mutationFn: (aliasId: string) => api.deleteEntityAlias(entityId, aliasId),
		onSuccess: () => invalidateEntity(entityId),
	});

	const decide = useMutation({
		mutationFn: ({ fact, accept }: { fact: EntityFact; accept: boolean }) =>
			accept ? api.acceptFact(fact.id) : api.rejectFact(fact.id),
		onMutate: async ({ fact, accept }) => {
			// Decide in the cache first: a review list must feel instant.
			const key = qk.entityFacts(entityId);
			await queryClient.cancelQueries({ queryKey: key });
			const previous = queryClient.getQueryData<EntityFact[]>(key);
			queryClient.setQueryData<EntityFact[]>(key, (current) =>
				(current ?? []).map((row) =>
					row.id === fact.id ? { ...row, status: accept ? "accepted" : "rejected" } : row,
				),
			);
			return { previous, key };
		},
		onError: (_error, _vars, context) => {
			if (context?.previous) queryClient.setQueryData(context.key, context.previous);
		},
		onSettled: () => invalidateEntity(entityId),
	});

	const saveFact = async (draft: FactDraft) => {
		const chapter = story.data?.chapters.find((item) => item.id === draft.chapterId);
		const value: Record<string, unknown> =
			draft.valueType === "number"
				? { value_number: Number(draft.value) }
				: draft.valueType === "date"
					? { value_date: draft.value }
					: { value_text: draft.value };
		const payload = {
			predicate: draft.predicate.trim(),
			value_type: draft.valueType,
			chapter_id: draft.chapterId,
			quote: draft.quote.trim() || null,
			line_start: draft.lineStart ? Number(draft.lineStart) : null,
			confidence: draft.confidence,
			status: draft.status,
			valid_from_chapter: draft.validFrom ? Number(draft.validFrom) : chapter?.chapter_number ?? null,
			valid_to_chapter: draft.validTo ? Number(draft.validTo) : null,
			...value,
		};
		if (factDialog?.fact) {
			await api.updateFact(factDialog.fact.id, payload);
		} else {
			await api.createFact(entityId, payload);
		}
		await invalidateEntity(entityId);
	};

	const createRelationship = useMutation({
		mutationFn: () =>
			api.createRelationship(entityId, {
				to_entity_id: relTarget,
				relationship_type: relType.trim(),
				description: relDescription.trim(),
			}),
		onSuccess: async () => {
			setRelOpen(false);
			setRelType("");
			setRelTarget("");
			setRelDescription("");
			toast.success("Relationship added.");
			await queryClient.invalidateQueries({ queryKey: qk.entityRelationships(entityId) });
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That relationship could not be added."),
	});

	const updateRelationship = useMutation({
		mutationFn: (edit: { id: string; type: string; description: string }) =>
			api.updateRelationship(edit.id, {
				relationship_type: edit.type.trim(),
				description: edit.description.trim(),
			}),
		onSuccess: async () => {
			setRelEdit(null);
			toast.success("Relationship updated.");
			await queryClient.invalidateQueries({ queryKey: qk.entityRelationships(entityId) });
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That relationship could not be saved."),
	});

	const removeRelationship = useMutation({
		mutationFn: (id: string) => api.deleteRelationship(id),
		onSuccess: async () => {
			toast.success("Relationship removed.");
			await queryClient.invalidateQueries({ queryKey: qk.entityRelationships(entityId) });
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That relationship could not be removed."),
	});

	const archiveEntry = useMutation({
		mutationFn: () => api.archiveEntity(entityId),
		onSuccess: async () => {
			toast.success("Entry archived.");
			await queryClient.invalidateQueries({ queryKey: qk.entityList(storyId) });
			router.push(`/stories/${storyId}/wiki`);
		},
		onError: (error) => toast.error(error instanceof Error ? error.message : "That entry could not be archived."),
	});

	async function deleteFact(fact: EntityFact) {
		const ok = await confirm({
			title: "Delete this fact?",
			description: "The value and its provenance will be removed. This cannot be undone.",
			confirmLabel: "Delete fact",
			destructive: true,
		});
		if (!ok) return;
		try {
			await api.deleteFact(fact.id);
			toast.success("Fact deleted.");
			await invalidateEntity(entityId);
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "That fact could not be deleted.");
		}
	}

	async function confirmRemoveRelationship(row: EntityRelationship) {
		const ok = await confirm({
			title: "Remove this relationship?",
			description: `Remove “${row.relationship_type.replace(/_/g, " ")}” between ${detailType(row.from_entity_id)} and ${detailType(row.to_entity_id)}.`,
			confirmLabel: "Remove",
			destructive: true,
		});
		if (ok) removeRelationship.mutate(row.id);
	}

	function detailType(id: string) {
		return nameById.get(id) ?? "the entry";
	}

	if (entity.isPending) {
		return <div className="wiki-detail"><p className="wiki-quiet">Opening this entry…</p></div>;
	}

	if (entity.error || !entity.data) {
		return (
			<div className="wiki-empty" role="alert">
				<h2>That entry is not available.</h2>
				<p>{entity.error instanceof Error ? entity.error.message : "It may have been merged or archived."}</p>
				<Link className="button button-primary" href={`/stories/${storyId}/wiki`}>
					Back to the wiki
				</Link>
			</div>
		);
	}

	const detail = entity.data;
	const lastAppearance = facts.data?.[0];
	return (
		<div className="wiki-detail">
			<header className="wiki-detail-head">
				<div className="wiki-detail-title">
					<Link className="text-button subtle" href={`/stories/${storyId}/wiki`}>
						← All entries
					</Link>
					<h1>{detail.name}</h1>
					<div className="wiki-detail-badges">
						<span className="wiki-type-chip">{entityTypeLabel(detail.entity_type)}</span>
						<span className={`wiki-status-chip status-${detail.status}`}>{capitalise(detail.status)}</span>
						{detail.first_chapter_number && <span className="wiki-quiet">first seen ch. {detail.first_chapter_number}</span>}
						{detail.last_chapter_number && <span className="wiki-quiet">last seen ch. {detail.last_chapter_number}</span>}
					</div>
				</div>
				<div className="wiki-detail-actions">
					{lastAppearance && (
						<Link
							className="button button-quiet"
							href={`/stories/${storyId}?chapter=${lastAppearance.chapter_id}&line=${lastAppearance.line_start}`}
						>
							Open last appearance
						</Link>
					)}
					<button className="quiet-button" onClick={() => setEditing((value) => !value)}>
						{editing ? "Done editing" : "Edit entry"}
					</button>
					<button className="quiet-button" onClick={() => setMergeOpen(true)}>
						Merge into…
					</button>
					<button
						className="quiet-button"
						disabled={archiveEntry.isPending}
						onClick={async () => {
							const ok = await confirm({
								title: "Archive this entry?",
								description: "It leaves the active wiki but stays in the database and can be restored from the archived filter.",
								confirmLabel: "Archive entry",
							});
							if (ok) archiveEntry.mutate();
						}}
					>
						{archiveEntry.isPending ? "Archiving…" : "Archive entry"}
					</button>
				</div>
			</header>

			{editing ? (
				<form
					className="wiki-form wiki-edit-form"
					onSubmit={async (event) => {
						event.preventDefault();
						const form = new FormData(event.currentTarget);
						await api.updateEntity(entityId, {
							name: String(form.get("name") ?? detail.name),
							entity_type: normalizeEntityType(String(form.get("type") ?? detail.entity_type)),
							summary: String(form.get("summary") ?? detail.summary),
						});
						toast.success("Entry updated.");
						setEditing(false);
						await invalidateEntity(entityId);
					}}
				>
					<label>
						<span>Name</span>
						<input name="name" defaultValue={detail.name} maxLength={200} />
					</label>
					<label>
						<span>Type</span>
						<input name="type" defaultValue={detail.entity_type} list="entity-type-edit-suggestions" maxLength={32} />
						<datalist id="entity-type-edit-suggestions">
							{ENTITY_TYPES.map((value) => (
								<option key={value} value={value}>
									{ENTITY_TYPE_LABELS[value]}
								</option>
							))}
						</datalist>
						<small>Any label works. Spaces become underscores.</small>
					</label>
					<label>
						<span>Summary</span>
						<textarea name="summary" rows={3} defaultValue={detail.summary} />
					</label>
					<div className="dialog-actions">
						<button type="button" className="quiet-button" onClick={() => setEditing(false)}>
							Cancel
						</button>
						<button className="button button-primary" type="submit">
							Save entry
						</button>
					</div>
				</form>
			) : (
				<section className="wiki-detail-section" aria-labelledby="summary-heading">
					<header className="wiki-section-head">
						<h2 id="summary-heading">Summary</h2>
						{summaryDraft === null && (
							<button className="text-button" onClick={() => setSummaryDraft(detail.summary)}>
								Edit
							</button>
						)}
					</header>
					{summaryDraft === null ? (
						<p className={detail.summary ? "wiki-summary" : "wiki-quiet"}>
							{detail.summary || "No summary yet. Write one in your own words; AI never overwrites it."}
						</p>
					) : (
						<div className="wiki-summary-editor">
							<textarea
								rows={4}
								value={summaryDraft}
								onChange={(event) => setSummaryDraft(event.target.value)}
								autoFocus
							/>
							<div className="dialog-actions">
								<button className="quiet-button" onClick={() => setSummaryDraft(null)}>
									Cancel
								</button>
								<button
									className="button button-primary"
									disabled={saveSummary.isPending}
									onClick={() => saveSummary.mutate(summaryDraft)}
								>
									{saveSummary.isPending ? "Saving…" : "Save summary"}
								</button>
							</div>
						</div>
					)}
				</section>
			)}

			<section className="wiki-detail-section" aria-labelledby="aliases-heading">
				<header className="wiki-section-head">
					<h2 id="aliases-heading">Aliases</h2>
					<button className="text-button" onClick={() => setAddingAlias(true)}>
						Add alias
					</button>
				</header>
				<div className="alias-chips">
					{detail.aliases.map((alias) => (
						<span className={`alias-chip type-${alias.alias_type}`} key={alias.id}>
							{alias.alias}
							{alias.alias !== detail.name && (
								<button
									aria-label={`Remove alias ${alias.alias}`}
									onClick={() => removeAlias.mutate(alias.id)}
									disabled={removeAlias.isPending}
								>
									×
								</button>
							)}
						</span>
					))}
					{!detail.aliases.length && <span className="wiki-quiet">No aliases yet.</span>}
				</div>
				{addingAlias && (
					<form
						className="alias-form"
						onSubmit={(event) => {
							event.preventDefault();
							if (!aliasDraft.trim()) return;
							addAlias.mutate(aliasDraft.trim());
						}}
					>
						<input
							autoFocus
							value={aliasDraft}
							onChange={(event) => setAliasDraft(event.target.value)}
							placeholder="the captain"
							maxLength={200}
							aria-label="New alias"
						/>
						<button className="button button-primary" type="submit" disabled={addAlias.isPending}>
							Add
						</button>
						<button type="button" className="quiet-button" onClick={() => setAddingAlias(false)}>
							Cancel
						</button>
					</form>
				)}
				{addAlias.error instanceof Error && <p className="form-error">{addAlias.error.message}</p>}
			</section>

			<FactSection
				storyId={storyId}
				entityId={entityId}
				onAdd={() => setFactDialog({ fact: null })}
				onEdit={(fact) => setFactDialog({ fact })}
				onAccept={(fact) => decide.mutate({ fact, accept: true })}
				onReject={(fact) => decide.mutate({ fact, accept: false })}
				onDelete={(fact) => void deleteFact(fact)}
				busyId={decide.isPending ? decide.variables?.fact.id ?? "" : ""}
				entityNames={nameById}
			/>

			<section className="wiki-detail-section" aria-labelledby="relationships-heading">
				<header className="wiki-section-head">
					<h2 id="relationships-heading">Relationships</h2>
					<button className="text-button" onClick={() => setRelOpen((value) => !value)}>
						{relOpen ? "Close" : "Add relationship"}
					</button>
				</header>
				{relOpen && (
					<form
						className="relationship-form"
						onSubmit={(event) => {
							event.preventDefault();
							if (!relType.trim() || !relTarget) return;
							createRelationship.mutate();
						}}
					>
						<input
							value={relType}
							onChange={(event) => setRelType(event.target.value)}
							placeholder="rumoured rival of"
							aria-label="Relationship type"
							maxLength={60}
						/>
						<select value={relTarget} onChange={(event) => setRelTarget(event.target.value)} aria-label="Target entity">
							<option value="">Choose an entry…</option>
							{(allEntities.data ?? [])
								.filter((row) => row.id !== entityId)
								.map((row) => (
									<option key={row.id} value={row.id}>
										{row.name} · {entityTypeLabel(row.entity_type)}
									</option>
								))}
						</select>
						<input
							value={relDescription}
							onChange={(event) => setRelDescription(event.target.value)}
							placeholder="Optional note: how they know each other"
							aria-label="Relationship description"
							maxLength={4000}
						/>
						<button className="button button-primary" type="submit" disabled={createRelationship.isPending}>
							Add
						</button>
					</form>
				)}
				{createRelationship.error instanceof Error && <p className="form-error">{createRelationship.error.message}</p>}
				{relationships.isPending ? (
					<p className="wiki-quiet">Loading relationships…</p>
				) : (
					<div className="relationship-columns">
						<div>
							<h3>Outgoing</h3>
							{(relationships.data?.outgoing ?? []).map((row) => (
								<div className="relationship-row" key={row.id}>
									<div className="relationship-row-copy">
										<strong>{row.relationship_type.replace(/_/g, " ")}</strong>
										<span>{nameById.get(row.to_entity_id) ?? row.to_entity_id.slice(0, 8)}</span>
										{row.description && <small>{row.description}</small>}
									</div>
									<div className="relationship-row-actions">
										<button className="text-button subtle" onClick={() => setRelEdit({ id: row.id, type: row.relationship_type, description: row.description })}>Edit</button>
										<button className="text-button subtle" onClick={() => void confirmRemoveRelationship(row)}>Remove</button>
									</div>
									{relEdit?.id === row.id && (
										<form
											className="relationship-edit"
											onSubmit={(event) => {
												event.preventDefault();
												if (relEdit.type.trim()) updateRelationship.mutate(relEdit);
											}}
										>
											<input value={relEdit.type} onChange={(event) => setRelEdit({ ...relEdit, type: event.target.value })} aria-label="Relationship type" maxLength={60} autoFocus />
											<input value={relEdit.description} onChange={(event) => setRelEdit({ ...relEdit, description: event.target.value })} aria-label="Relationship description" placeholder="A note, if useful" maxLength={4000} />
											<div className="relationship-edit-actions">
												<button className="button button-approve" type="submit" disabled={updateRelationship.isPending}>{updateRelationship.isPending ? "Saving…" : "Save"}</button>
												<button className="text-button subtle" type="button" onClick={() => setRelEdit(null)}>Cancel</button>
											</div>
										</form>
									)}
								</div>
							))}
							{!(relationships.data?.outgoing ?? []).length && <p className="wiki-quiet">None yet.</p>}
						</div>
						<div>
							<h3>Incoming</h3>
							{(relationships.data?.incoming ?? []).map((row) => (
								<div className="relationship-row" key={row.id}>
									<div className="relationship-row-copy">
										<strong>{row.relationship_type.replace(/_/g, " ")}</strong>
										<span>{nameById.get(row.from_entity_id) ?? row.from_entity_id.slice(0, 8)}</span>
										{row.description && <small>{row.description}</small>}
									</div>
									<div className="relationship-row-actions">
										<button className="text-button subtle" onClick={() => setRelEdit({ id: row.id, type: row.relationship_type, description: row.description })}>Edit</button>
										<button className="text-button subtle" onClick={() => void confirmRemoveRelationship(row)}>Remove</button>
									</div>
									{relEdit?.id === row.id && (
										<form
											className="relationship-edit"
											onSubmit={(event) => {
												event.preventDefault();
												if (relEdit.type.trim()) updateRelationship.mutate(relEdit);
											}}
										>
											<input value={relEdit.type} onChange={(event) => setRelEdit({ ...relEdit, type: event.target.value })} aria-label="Relationship type" maxLength={60} autoFocus />
											<input value={relEdit.description} onChange={(event) => setRelEdit({ ...relEdit, description: event.target.value })} aria-label="Relationship description" placeholder="A note, if useful" maxLength={4000} />
											<div className="relationship-edit-actions">
												<button className="button button-approve" type="submit" disabled={updateRelationship.isPending}>{updateRelationship.isPending ? "Saving…" : "Save"}</button>
												<button className="text-button subtle" type="button" onClick={() => setRelEdit(null)}>Cancel</button>
											</div>
										</form>
									)}
								</div>
							))}
							{!(relationships.data?.incoming ?? []).length && <p className="wiki-quiet">None yet.</p>}
						</div>
					</div>
				)}
			</section>

			<section className="wiki-detail-section" aria-labelledby="appearances-heading">
				<header className="wiki-section-head">
					<h2 id="appearances-heading">Appearances and sources</h2>
					<span className="wiki-quiet">{appearanceChapters.length} {appearanceChapters.length === 1 ? "chapter" : "chapters"}</span>
				</header>
				{facts.isPending ? (
					<p className="wiki-quiet">Loading passages…</p>
				) : (facts.data ?? []).length === 0 ? (
					<p className="wiki-quiet">This name has not been found in the manuscript yet.</p>
				) : (
					<ol className="appearance-list">
						{appearanceChapters.map((chapter) => (
							<li key={chapter.chapter_id}>
								<Link
									className="appearance-row"
									href={`/stories/${storyId}?chapter=${chapter.chapter_id}`}
								>
									<span className="appearance-chapter">
										Ch. {chapter.chapter_number} · {chapter.chapter_title}
									</span>
								</Link>
							</li>
						))}
					</ol>
				)}
			</section>

			<section className="wiki-detail-section" aria-labelledby="threads-heading">
				<header className="wiki-section-head">
					<h2 id="threads-heading">Threads</h2>
					<Link className="text-button" href={`/stories/${storyId}/wiki/threads`}>
						All threads
					</Link>
				</header>
				{linkedThreads.length === 0 ? (
					<p className="wiki-quiet">No thread links to this entry yet.</p>
				) : (
					<ul className="detail-thread-list">
						{linkedThreads.map((thread) => (
							<li key={thread.id}>
								<span className={`thread-state state-${thread.state}`}>{thread.state}</span>
								<strong>{thread.title}</strong>
								{thread.setup_quote && <blockquote>“{thread.setup_quote}”</blockquote>}
							</li>
						))}
					</ul>
				)}
			</section>

			{factDialog && (
				<FactDialog
					story={story.data}
					entityName={detail.name}
					suggestions={[...new Set((factRows.data ?? []).map((fact) => fact.predicate))]}
					initial={
						factDialog.fact
							? draftFromFact(factDialog.fact, story.data?.chapters[0]?.id ?? "")
							: { ...EMPTY_FACT, chapterId: story.data?.chapters[0]?.id ?? "" }
					}
					onClose={() => setFactDialog(null)}
					onSave={saveFact}
				/>
			)}
			{mergeOpen && (
				<MergeDialog
					storyId={storyId}
					entity={detail}
					onClose={() => setMergeOpen(false)}
					onMerged={async (target) => {
						setMergeOpen(false);
						toast.success(`Merged into ${target.name}.`, {
							action: {
								label: "Undo",
								onClick: async () => {
									await api.unmergeEntity(entityId);
									await invalidateEntity(entityId);
									await invalidateEntity(target.id);
									toast.success("Merge undone.");
								},
							},
							duration: 12_000,
						});
						await invalidateEntity(entityId);
						await invalidateEntity(target.id);
						router.push(`/stories/${storyId}/wiki/${target.id}`);
					}}
				/>
			)}
			{addingAlias && addAlias.isPending && <p className="wiki-quiet">Adding alias…</p>}
		</div>
	);
}
