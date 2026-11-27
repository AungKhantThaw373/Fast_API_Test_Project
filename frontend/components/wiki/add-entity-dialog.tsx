"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";

import { api, type WikiEntity, type WikiFormat } from "@/lib/api";
import { normalizeEntityType, typeOptionsFor } from "@/components/wiki/wiki-filters";
import { toast } from "sonner";

export interface EntityDraft {
	name: string;
	entityType: string;
	summary: string;
	alias: string;
	quote: string;
}

export const EMPTY_DRAFT: EntityDraft = {
	name: "",
	entityType: "character",
	summary: "",
	alias: "",
	quote: "",
};

export function AddEntityDialog({
	storyId,
	initial,
	onClose,
	onCreated,
	title = "New wiki entry",
	chapterId,
	format,
}: {
	storyId: string;
	initial?: Partial<EntityDraft>;
	onClose: () => void;
	onCreated: (entity: WikiEntity) => void;
	title?: string;
	chapterId?: string | null;
	format?: WikiFormat | null;
}) {
	const [draft, setDraft] = useState<EntityDraft>({ ...EMPTY_DRAFT, ...initial });
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState("");

	async function submit(event: React.FormEvent) {
		event.preventDefault();
		if (!draft.name.trim()) {
			setError("A name is the one thing this needs.");
			return;
		}
		setSaving(true);
		setError("");
		try {
			const created = await api.createEntity(storyId, {
				name: draft.name.trim(),
				entity_type: normalizeEntityType(draft.entityType),
				summary: draft.summary.trim(),
				aliases: draft.alias.trim() ? [{ alias: draft.alias.trim(), alias_type: "title" }] : [],
			});
			// A captured quote becomes the first fact, with real provenance.
			if (draft.quote.trim() && chapterId) {
				try {
					await api.createFact(created.id, {
						predicate: "summary",
						value_text: draft.summary.trim() || draft.quote.trim(),
						chapter_id: chapterId,
						quote: draft.quote.trim(),
						status: "accepted",
					});
				} catch {
					toast.warning("Entry saved, but the captured quote could not be attached.");
				}
			}
			toast.success(`${created.name} is in the wiki.`);
			onCreated(created);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : "Could not save that entry.");
		} finally {
			setSaving(false);
		}
	}

	return (
		<Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card" aria-describedby="add-entity-hint">
					<Dialog.Title className="dialog-title">{title}</Dialog.Title>
					<Dialog.Description id="add-entity-hint" className="dialog-hint">
						One field is enough to begin. Facts, aliases, and sources can follow.
					</Dialog.Description>
					<form className="wiki-form" onSubmit={submit}>
						<label>
							<span>Name</span>
							<input
								autoFocus
								value={draft.name}
								onChange={(event) => setDraft({ ...draft, name: event.target.value })}
								maxLength={200}
								placeholder="Mira Voss"
							/>
						</label>
						<label>
							<span>Type</span>
							<input
								list="entity-type-suggestions"
								value={draft.entityType}
								onChange={(event) => setDraft({ ...draft, entityType: event.target.value })}
								placeholder="character, faction, curse…"
								maxLength={32}
							/>
							<datalist id="entity-type-suggestions">
								{typeOptionsFor(format).map((type) => (
									<option key={type} value={type}>
										{format?.types.find((item) => item.key === type)?.label ?? type}
									</option>
								))}
							</datalist>
							<small>These are the types in your format. Type another name if this entry needs its own kind.</small>
						</label>
						<label>
							<span>Summary</span>
							<textarea
								rows={3}
								value={draft.summary}
								onChange={(event) => setDraft({ ...draft, summary: event.target.value })}
								placeholder="Who or what is this, in your own words?"
							/>
						</label>
						<label>
							<span>Also known as</span>
							<input
								value={draft.alias}
								onChange={(event) => setDraft({ ...draft, alias: event.target.value })}
								placeholder="the captain, Lady Voss"
							/>
						</label>
						{draft.quote.trim() && (
							<div className="wiki-capture-note">
								<strong>Captured quote</strong>
								<blockquote>“{draft.quote.trim()}”</blockquote>
							</div>
						)}
						{error && <p className="form-error" role="alert">{error}</p>}
						<div className="dialog-actions">
							<Dialog.Close asChild>
								<button type="button" className="quiet-button">
									Cancel
								</button>
							</Dialog.Close>
							<button className="button button-primary" type="submit" disabled={saving}>
								{saving ? "Saving…" : "Add to wiki"}
							</button>
						</div>
					</form>
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}
