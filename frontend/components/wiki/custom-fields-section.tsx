"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { ProvenanceChip } from "@/components/wiki/provenance-chip";
import { api, type EntityFact, type WikiFieldDefinition } from "@/lib/api";

function valueOf(fact: EntityFact): string {
	if (fact.value_number !== null) return String(fact.value_number);
	if (fact.value_date !== null) return fact.value_date;
	return fact.value_text ?? "";
}

function latestFact(facts: EntityFact[], key: string): EntityFact | undefined {
	return facts
		.filter((fact) => fact.predicate === key && fact.status !== "rejected" && fact.status !== "superseded")
		.sort((a, b) => {
			if (a.status === "accepted" && b.status !== "accepted") return -1;
			if (b.status === "accepted" && a.status !== "accepted") return 1;
			return b.created_at.localeCompare(a.created_at);
		})[0];
}

/** The writer-defined fields shown at the top of an entry. Each value is a
 * fact, so a field keeps the same provenance and review rules as any other
 * fact. Fields are only decorative when they have no value yet. */
export function CustomFieldsSection({
	storyId,
	entityId,
	fields,
	facts,
	chapters,
	onChanged,
}: {
	storyId: string;
	entityId: string;
	fields: WikiFieldDefinition[];
	facts: EntityFact[];
	chapters: { id: string; chapter_number: number }[];
	onChanged: () => Promise<void> | void;
}) {
	const confirm = useConfirm();
	const [editing, setEditing] = useState<string | null>(null);
	const [draft, setDraft] = useState("");
	const [saving, setSaving] = useState<string | null>(null);

	if (!fields.length) return null;

	function start(key: string, fact?: EntityFact) {
		setEditing(key);
		setDraft(fact ? valueOf(fact) : "");
	}

	async function save(key: string, fact?: EntityFact) {
		const value = draft.trim();
		if (!value) {
			toast.error("A field needs a value. Use Clear to remove it.");
			return;
		}
		setSaving(key);
		try {
			if (fact) {
				await api.updateFact(fact.id, {
					value_text: value,
					value_number: null,
					value_date: null,
					value_type: "text",
				});
				if (fact.status !== "accepted") await api.acceptFact(fact.id);
			} else {
				await api.createFact(entityId, {
					predicate: key,
					value_text: value,
					value_type: "text",
					status: "accepted",
					confidence: 100,
					context: { source: "manual_wiki_field" },
				});
			}
			setEditing(null);
			setDraft("");
			await onChanged();
			toast.success("Field saved.");
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : "That field could not be saved.");
		} finally {
			setSaving(null);
		}
	}

	async function remove(key: string, fact: EntityFact) {
		const ok = await confirm({
			title: "Clear this field?",
			description: "The fact and its provenance are removed. This cannot be undone.",
			confirmLabel: "Clear field",
			destructive: true,
		});
		if (!ok) return;
		setSaving(key);
		try {
			await api.deleteFact(fact.id);
			await onChanged();
			toast.success("Field cleared.");
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : "That field could not be cleared.");
		} finally {
			setSaving(null);
		}
	}

	return (
		<section className="wiki-detail-section wiki-fields-section" aria-labelledby="details-heading">
			<header className="wiki-section-head">
				<h2 id="details-heading">Details</h2>
				<span className="wiki-quiet">Fields from your story format</span>
			</header>
			<dl className="wiki-field-list">
				{fields.map((field) => {
					const fact = latestFact(facts, field.key);
					const chapter = fact?.chapter_id ? chapters.find((item) => item.id === fact.chapter_id) : undefined;
					const isEditing = editing === field.key;
					return (
						<div className="wiki-field-row" key={field.key}>
							<dt title={field.hint}>
								{field.label}
								{field.hint && <small>{field.hint}</small>}
							</dt>
							<dd>
								{isEditing ? (
									<div className="wiki-field-editor">
										<input
											autoFocus
											value={draft}
											onChange={(event) => setDraft(event.target.value)}
											onKeyDown={(event) => {
												if (event.key === "Enter") void save(field.key, fact);
												if (event.key === "Escape") setEditing(null);
											}}
											aria-label={field.label}
										/>
										<button type="button" className="button button-primary" disabled={saving === field.key} onClick={() => void save(field.key, fact)}>
											{saving === field.key ? "Saving…" : "Save"}
										</button>
										<button type="button" className="text-button subtle" onClick={() => setEditing(null)}>Cancel</button>
									</div>
								) : (
									<div className="wiki-field-value">
										{fact ? (
											<>
												<span>{valueOf(fact) || "—"}</span>
												<ProvenanceChip
													storyId={storyId}
													chapterId={fact.chapter_id}
													chapterNumber={chapter?.chapter_number ?? null}
													line={fact.line_start}
													quote={fact.quote}
												/>
												{fact.status !== "accepted" && <span className={`wiki-status-chip status-${fact.status}`}>{fact.status}</span>}
											</>
										) : (
											<span className="wiki-quiet">Not set</span>
										)}
										<button type="button" className="text-button" onClick={() => start(field.key, fact)}>
											{fact ? "Edit" : "Add"}
										</button>
										{fact && (
											<button type="button" className="text-button subtle" disabled={saving === field.key} onClick={() => void remove(field.key, fact)}>
												Clear
											</button>
										)}
									</div>
								)}
							</dd>
						</div>
					);
				})}
			</dl>
		</section>
	);
}
