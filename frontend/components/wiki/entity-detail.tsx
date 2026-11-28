"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { CustomFieldsSection } from "@/components/wiki/custom-fields-section";
import { FactDialog, EMPTY_FACT, draftFromFact, type FactDraft } from "@/components/wiki/fact-dialog";
import { FactSection } from "@/components/wiki/fact-section";
import { MergeDialog } from "@/components/wiki/merge-dialog";
import { WikiFieldDialog } from "@/components/wiki/wiki-field-dialog";
import { useStoryWikiFormat } from "@/components/wiki/wiki-format-context";
import {
	useEntities,
	useEntity,
	useEntityAppearances,
	useEntityFacts,
	useEntityRelationships,
	useStory,
	useThreads,
} from "@/components/wiki/use-wiki";
import { capitalise, entityTypeLabel, normalizeEntityType, typeOptionsFor } from "@/components/wiki/wiki-filters";
import { api, type EntityFact, type EntityRelationship, type WikiEntryType, type WikiFieldDefinition, type WikiSectionKey } from "@/lib/api";
import { qk } from "@/lib/query-keys";

const PAGE_CARDS: { key: WikiSectionKey; label: string }[] = [
	{ key: "summary", label: "Summary" },
	{ key: "facts", label: "Facts" },
	{ key: "relationships", label: "Relationships" },
	{ key: "aliases", label: "Aliases" },
	{ key: "threads", label: "Threads" },
];

export function EntityDetail({ storyId, entityId }: { storyId: string; entityId: string }) {
	const router = useRouter();
	const format = useStoryWikiFormat();
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
	const [layoutEditing, setLayoutEditing] = useState(false);
	const [layoutSaving, setLayoutSaving] = useState(false);
	const [fieldDialog, setFieldDialog] = useState<{ field: WikiFieldDefinition | null } | null>(null);

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

	const relationshipRows = [
		...(relationships.data?.outgoing ?? []).map((row) => ({ row, outgoing: true, otherId: row.to_entity_id })),
		...(relationships.data?.incoming ?? []).map((row) => ({ row, outgoing: false, otherId: row.from_entity_id })),
	];

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
		const chapterId = draft.chapterId || null;
		const payload = {
			predicate: draft.predicate.trim(),
			value_type: draft.valueType,
			chapter_id: chapterId,
			quote: chapterId ? draft.quote.trim() || null : null,
			line_start: chapterId && draft.lineStart ? Number(draft.lineStart) : null,
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
	const typeConfig = format?.types.find((item) => item.key === detail.entity_type);
	const sectionOn = (key: WikiSectionKey) => (key === "appearances" ? true : typeConfig ? typeConfig.sections[key] : true);
	const customFields = typeConfig?.fields ?? [];
	const configuredPredicates = new Set(customFields.map((field) => field.key));
	const typeOptions = typeOptionsFor(format);

	async function writeType(nextType: WikiEntryType) {
		if (!format || !typeConfig) throw new Error("This entry type is not in the story format yet.");
		const next = structuredClone(format);
		const index = next.types.findIndex((item) => item.key === typeConfig.key);
		if (index < 0) throw new Error("This entry type is not in the story format yet.");
		next.types[index] = nextType;
		setLayoutSaving(true);
		try {
			await api.updateWikiFormat(storyId, next);
			await queryClient.invalidateQueries({ queryKey: qk.wikiFormat(storyId) });
		} finally {
			setLayoutSaving(false);
		}
	}

	async function setSectionVisible(key: WikiSectionKey, visible: boolean) {
		if (!typeConfig || key === "appearances") return;
		try {
			await writeType({ ...typeConfig, sections: { ...typeConfig.sections, [key]: visible } });
			toast.success(visible ? "Card added back." : "Card hidden. Its entries and sources are untouched.");
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : "That card could not be changed.");
		}
	}

	async function saveFieldDefinition(field: WikiFieldDefinition) {
		if (!typeConfig) throw new Error("This entry type is not in the story format yet.");
		const existing = fieldDialog?.field;
		if (!existing && typeConfig.fields.some((item) => item.key === field.key)) {
			throw new Error("A field with that key already exists. Edit it instead.");
		}
		const fields = existing
			? typeConfig.fields.map((item) => (item.key === existing.key ? field : item))
			: [...typeConfig.fields, field];
		try {
			await writeType({ ...typeConfig, fields });
			setFieldDialog(null);
			toast.success(existing ? "Field updated." : "Field added.");
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : "That field could not be saved.");
			throw cause;
		}
	}

	async function removeFieldDefinition(field: WikiFieldDefinition) {
		if (!typeConfig) return;
		const ok = await confirm({
			title: `Remove the “${field.label}” field?`,
			description: "This removes the field from the page, not its values. Existing values stay in Facts, with their sources, and can be added back under the same key.",
			confirmLabel: "Remove field",
			destructive: true,
		});
		if (!ok) return;
		try {
			await writeType({ ...typeConfig, fields: typeConfig.fields.filter((item) => item.key !== field.key) });
			toast.success("Field removed. Its values remain in Facts.");
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : "That field could not be removed.");
		}
	}
	return (
		<div className="wiki-detail">
			<header className="wiki-detail-head">
				<div className="wiki-detail-title">
					<Link className="text-button subtle" href={`/stories/${storyId}/wiki`}>
						← All entries
					</Link>
					<h1>{detail.name}</h1>
					<div className="wiki-detail-badges">
						<span className="wiki-type-chip">{entityTypeLabel(detail.entity_type, format)}</span>
						<span className={`wiki-status-chip status-${detail.status}`}>{capitalise(detail.status)}</span>
						{detail.first_chapter_number && <span className="wiki-quiet">first seen ch. {detail.first_chapter_number}</span>}
						{detail.last_chapter_number && <span className="wiki-quiet">last seen ch. {detail.last_chapter_number}</span>}
					</div>
				</div>
				<div className="wiki-detail-actions">
					{typeConfig && (
						<button className="quiet-button" onClick={() => setLayoutEditing((value) => !value)}>
							{layoutEditing ? "Done customising" : "Customise page"}
						</button>
					)}
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

			{layoutEditing && (
				<section className="wiki-page-panel" aria-label="Page cards">
					<div className="wiki-page-panel-head">
						<strong>Page cards</strong>
						<span>Click a card to show or hide it. Nothing is deleted.</span>
					</div>
					{!typeConfig ? (
						<p className="wiki-quiet">This entry type is not in the story format yet. Use Format in the sidebar first.</p>
					) : (
						<>
							<div className="wiki-card-toggles">
								{PAGE_CARDS.map((card) => {
									const visible = sectionOn(card.key);
									return (
										<button
											key={card.key}
											className={`wiki-card-add${visible ? " is-on" : ""}`}
											aria-pressed={visible}
											disabled={layoutSaving}
											onClick={() => void setSectionVisible(card.key, !visible)}
										>
											{visible ? "✓" : "＋"} {card.label}
										</button>
									);
								})}
								<span className="wiki-card-add is-locked">✓ Appearances · always</span>
								<button className="wiki-card-add" onClick={() => setFieldDialog({ field: null })}>＋ Field</button>
							</div>
							<p className="wiki-page-panel-note">Fields live in Details. Appearances and sources always stay.</p>
						</>
					)}
				</section>
			)}

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
							{typeOptions.map((value) => (
								<option key={value} value={value}>
									{entityTypeLabel(value, format)}
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
			) : sectionOn("summary") ? (
				<section className="wiki-detail-section" aria-labelledby="summary-heading">
					<header className="wiki-section-head">
						<h2 id="summary-heading">Summary</h2>
						{summaryDraft === null && (
							<div className="wiki-section-actions">
								{layoutEditing && typeConfig && (
									<button className="text-button subtle" disabled={layoutSaving} onClick={() => void setSectionVisible("summary", false)}>Hide</button>
								)}
								<button className="text-button" onClick={() => setSummaryDraft(detail.summary)}>
									Edit
								</button>
							</div>
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
			) : null}

			{sectionOn("aliases") && (
				<section className="wiki-detail-section" aria-labelledby="aliases-heading">
				<header className="wiki-section-head">
					<h2 id="aliases-heading">Aliases</h2>
					<div className="wiki-section-actions">
						{layoutEditing && typeConfig && (
							<button className="text-button subtle" disabled={layoutSaving} onClick={() => void setSectionVisible("aliases", false)}>Hide</button>
						)}
						<button className="text-button" onClick={() => setAddingAlias(true)}>
							Add alias
						</button>
					</div>
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
			)}

			{typeConfig && (customFields.length > 0 || layoutEditing) && (
				<CustomFieldsSection
					storyId={storyId}
					entityId={entityId}
					fields={customFields}
					facts={factRows.data ?? []}
					chapters={(story.data?.chapters ?? []).map((chapter) => ({ id: chapter.id, chapter_number: chapter.chapter_number }))}
					onChanged={() => invalidateEntity(entityId)}
					layoutEditing={layoutEditing}
					onAddField={() => setFieldDialog({ field: null })}
					onEditField={(field) => setFieldDialog({ field })}
					onRemoveField={(field) => void removeFieldDefinition(field)}
					onCustomise={() => setLayoutEditing(true)}
				/>
			)}

			{sectionOn("facts") && (
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
					hidePredicates={[...configuredPredicates]}
					onHide={layoutEditing && typeConfig ? () => void setSectionVisible("facts", false) : undefined}
					hideDisabled={layoutSaving}
				/>
			)}

			{sectionOn("relationships") && (
			<section className="wiki-detail-section" aria-labelledby="relationships-heading">
				<header className="wiki-section-head">
					<h2 id="relationships-heading">Relationships</h2>
					<div className="wiki-section-actions">
						{layoutEditing && typeConfig && (
							<button className="text-button subtle" disabled={layoutSaving} onClick={() => void setSectionVisible("relationships", false)}>Hide</button>
						)}
						<button className="text-button" onClick={() => setRelOpen((value) => !value)}>
							{relOpen ? "Close" : "Add relationship"}
						</button>
					</div>
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
										{row.name} · {entityTypeLabel(row.entity_type, format)}
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
				) : relationshipRows.length === 0 ? (
					<p className="wiki-quiet">None yet.</p>
				) : (
					<ul className="relationship-list">
						{relationshipRows.map(({ row, outgoing, otherId }) => (
							<li className="relationship-row" key={row.id}>
								<div className="relationship-row-copy">
									<span className="relationship-direction" aria-label={outgoing ? "Outgoing" : "Incoming"} title={outgoing ? "From this entry" : "To this entry"}>{outgoing ? "→" : "←"}</span>
									<strong>{nameById.get(otherId) ?? otherId.slice(0, 8)}</strong>
									<span className="relationship-type">{row.relationship_type.replace(/_/g, " ")}</span>
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
							</li>
						))}
					</ul>
				)}
			</section>
			)}

			{sectionOn("appearances") && (
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
			)}

			{sectionOn("threads") && (
			<section className="wiki-detail-section" aria-labelledby="threads-heading">
				<header className="wiki-section-head">
					<h2 id="threads-heading">Threads</h2>
					<div className="wiki-section-actions">
						{layoutEditing && typeConfig && (
							<button className="text-button subtle" disabled={layoutSaving} onClick={() => void setSectionVisible("threads", false)}>Hide</button>
						)}
						<Link className="text-button" href={`/stories/${storyId}/wiki/threads`}>
							All threads
						</Link>
					</div>
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
			)}

			{fieldDialog && typeConfig && (
				<WikiFieldDialog
					field={fieldDialog.field ?? undefined}
					existingKeys={customFields.map((field) => field.key)}
					onSave={saveFieldDefinition}
					onClose={() => setFieldDialog(null)}
				/>
			)}
			{factDialog && (
				<FactDialog
					story={story.data}
					entityName={detail.name}
					suggestions={[...new Set([...customFields.map((field) => field.key), ...(factRows.data ?? []).map((fact) => fact.predicate)])]}
					initial={
						factDialog.fact
							? draftFromFact(factDialog.fact)
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
