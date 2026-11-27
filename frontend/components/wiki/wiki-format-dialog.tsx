"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { api, type WikiEntryType, type WikiFormat, type WikiSectionKey } from "@/lib/api";
import { qk } from "@/lib/query-keys";

const SECTION_LABELS: { key: WikiSectionKey; label: string; hint: string }[] = [
	{ key: "summary", label: "Summary", hint: "The short opening description" },
	{ key: "facts", label: "Facts", hint: "Every sourced fact and detail" },
	{ key: "relationships", label: "Relationships", hint: "Who knows, loves, or opposes whom" },
	{ key: "aliases", label: "Aliases", hint: "Other names and titles" },
	{ key: "appearances", label: "Appearances", hint: "Chapters where the entry is seen" },
	{ key: "threads", label: "Threads", hint: "Open promises attached to the entry" },
];

const ALL_SECTIONS = {
	summary: true,
	facts: true,
	relationships: true,
	aliases: true,
	appearances: true,
	threads: true,
};

function slugKey(value: string): string {
	const slug = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 32);
	if (!slug) return "field";
	return /^[a-z]/.test(slug) ? slug : `type_${slug}`.slice(0, 32);
}

function uniqueKey(base: string, used: string[]): string {
	if (!used.includes(base)) return base;
	for (let index = 2; index < 100; index += 1) {
		const candidate = `${base.slice(0, 29)}_${index}`;
		if (!used.includes(candidate)) return candidate;
	}
	return `${base.slice(0, 27)}_new`;
}

function copy(format: WikiFormat): WikiFormat {
	return structuredClone(format);
}

export function WikiFormatDialog({
	storyId,
	format,
	onClose,
}: {
	storyId: string;
	format: WikiFormat;
	onClose: () => void;
}) {
	const queryClient = useQueryClient();
	const confirm = useConfirm();
	const [draft, setDraft] = useState<WikiFormat>(() => copy(format));
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState("");

	function updateType(index: number, patch: Partial<WikiEntryType>) {
		setDraft((current) => ({
			...current,
			types: current.types.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
		}));
	}

	function renameType(index: number, label: string) {
		const type = draft.types[index];
		const patch: Partial<WikiEntryType> = { label };
		if (type && type.key.startsWith("new_")) {
			patch.key = uniqueKey(slugKey(label), draft.types.map((item) => item.key));
		}
		updateType(index, patch);
	}

	function toggleSection(index: number, key: WikiSectionKey) {
		const type = draft.types[index];
		if (!type) return;
		updateType(index, { sections: { ...type.sections, [key]: !type.sections[key] } });
	}

	function addType() {
		const key = uniqueKey("new_type", draft.types.map((item) => item.key));
		setDraft((current) => ({
			...current,
			types: [...current.types, { key, label: "New type", description: "", sections: { ...ALL_SECTIONS }, fields: [] }],
		}));
	}

	async function removeType(index: number) {
		const type = draft.types[index];
		if (!type || draft.types.length === 1) return;
		const ok = await confirm({
			title: `Remove “${type.label}” from the format?`,
			description: "Existing entries of this type stay in the wiki and fall back to the full default layout. Nothing is deleted.",
			confirmLabel: "Remove type",
			destructive: true,
		});
		if (ok) setDraft((current) => ({ ...current, types: current.types.filter((_, itemIndex) => itemIndex !== index) }));
	}

	function updateField(typeIndex: number, fieldIndex: number, patch: { label?: string; key?: string; hint?: string }) {
		const type = draft.types[typeIndex];
		if (!type) return;
		const fields = type.fields.map((field, index) => {
			if (index !== fieldIndex) return field;
			const next = { ...field, ...patch };
			if (patch.label !== undefined && (field.key === "field" || field.key.startsWith("field_"))) {
				next.key = uniqueKey(slugKey(patch.label), type.fields.map((item) => item.key));
			}
			return next;
		});
		updateType(typeIndex, { fields });
	}

	function addField(typeIndex: number) {
		const type = draft.types[typeIndex];
		if (!type || type.fields.length >= 40) return;
		const key = uniqueKey("field", type.fields.map((item) => item.key));
		updateType(typeIndex, { fields: [...type.fields, { key, label: "New field", hint: "" }] });
	}

	function removeField(typeIndex: number, fieldIndex: number) {
		const type = draft.types[typeIndex];
		if (!type) return;
		updateType(typeIndex, { fields: type.fields.filter((_, index) => index !== fieldIndex) });
	}

	async function save() {
		if (draft.types.some((item) => !item.label.trim())) {
			setError("Every entry type needs a name.");
			return;
		}
		if (draft.types.some((item) => item.fields.some((field) => !field.label.trim()))) {
			setError("Every field needs a label.");
			return;
		}
		const typeKeys = draft.types.map((item) => item.key.trim());
		if (typeKeys.some((key) => !/^[a-z][a-z0-9_]{0,31}$/.test(key)) || new Set(typeKeys).size !== typeKeys.length) {
			setError("Stored keys must be unique and start with a lowercase letter. Use letters, numbers, and underscores.");
			return;
		}
		const badFields = draft.types.some((item) => {
			const keys = item.fields.map((field) => field.key.trim());
			return keys.some((key) => !/^[a-z][a-z0-9_]{0,31}$/.test(key)) || new Set(keys).size !== keys.length;
		});
		if (badFields) {
			setError("Field keys must be unique within a type and start with a lowercase letter. Use letters, numbers, and underscores.");
			return;
		}
		setSaving(true);
		setError("");
		try {
			await api.updateWikiFormat(storyId, {
				...draft,
				types: draft.types.map((item) => ({
					...item,
					label: item.label.trim(),
					fields: item.fields.map((field) => ({ ...field, label: field.label.trim(), hint: field.hint.trim() })),
				})),
			});
			await queryClient.invalidateQueries({ queryKey: qk.wikiFormat(storyId) });
			toast.success("Wiki format saved.");
			onClose();
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : "That format could not be saved.");
		} finally {
			setSaving(false);
		}
	}

	async function reset() {
		const ok = await confirm({
			title: "Restore the default wiki format?",
			description: "This replaces your types, sections, and fields with the starting skeleton. Entries and facts are untouched.",
			confirmLabel: "Restore default",
			destructive: true,
		});
		if (!ok) return;
		setSaving(true);
		setError("");
		try {
			const restored = await api.resetWikiFormat(storyId);
			setDraft(copy(restored));
			await queryClient.invalidateQueries({ queryKey: qk.wikiFormat(storyId) });
			toast.success("Default wiki format restored.");
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : "The format could not be reset.");
		} finally {
			setSaving(false);
		}
	}

	return (
		<Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card wiki-format-dialog" aria-describedby="wiki-format-hint">
					<Dialog.Title className="dialog-title">Shape this wiki</Dialog.Title>
					<Dialog.Description id="wiki-format-hint" className="dialog-hint">
						Choose which entry types exist, which sections each one shows, and the fields its entries use. AI extraction reads this format.
					</Dialog.Description>
					<div className="wiki-format-toolbar">
						<span>{draft.types.length} {draft.types.length === 1 ? "entry type" : "entry types"}</span>
						<button type="button" className="quiet-button" onClick={reset} disabled={saving}>Restore default</button>
					</div>
					<div className="wiki-format-body">
						{draft.types.map((type, typeIndex) => (
							<article className="wiki-format-type" key={`${type.key}-${typeIndex}`}>
								<div className="wiki-format-type-head">
									<div>
										<span className="wiki-format-key">{type.key}</span>
										<input
											aria-label={`Name for entry type ${typeIndex + 1}`}
											value={type.label}
											maxLength={80}
											onChange={(event) => renameType(typeIndex, event.target.value)}
										/>
									</div>
									<button type="button" className="text-button subtle" onClick={() => void removeType(typeIndex)} disabled={draft.types.length === 1}>
										Remove
									</button>
								</div>
								<label className="wiki-format-description">
									<span>What belongs here</span>
									<input
										value={type.description}
										maxLength={300}
										placeholder="A short hint the extractor can use"
										onChange={(event) => updateType(typeIndex, { description: event.target.value })}
									/>
								</label>
								<fieldset className="wiki-format-sections">
									<legend>Sections on an entry</legend>
									{SECTION_LABELS.map((section) => (
										<label key={section.key} title={section.hint}>
											<input
												type="checkbox"
												checked={type.sections[section.key]}
												onChange={() => toggleSection(typeIndex, section.key)}
											/>
											{section.label}
										</label>
									))}
								</fieldset>
								<div className="wiki-format-fields">
									<div className="wiki-format-fields-head">
										<strong>Fields</strong>
										<button type="button" className="text-button" onClick={() => addField(typeIndex)} disabled={type.fields.length >= 40}>Add field</button>
									</div>
									{type.fields.length === 0 && <p className="wiki-quiet">No fields. The entry still has a summary, facts, and whichever sections are on.</p>}
									{type.fields.map((field, fieldIndex) => (
										<div className="wiki-format-field" key={`${field.key}-${fieldIndex}`}>
											<input
												aria-label={`Field ${fieldIndex + 1} label`}
												value={field.label}
												maxLength={80}
												placeholder="Label"
												onChange={(event) => updateField(typeIndex, fieldIndex, { label: event.target.value })}
											/>
											<input
												aria-label={`Field ${fieldIndex + 1} stored key`}
												value={field.key}
												maxLength={32}
												className="wiki-format-field-key"
												onChange={(event) => updateField(typeIndex, fieldIndex, { key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })}
											/>
											<input
												aria-label={`Field ${fieldIndex + 1} hint`}
												value={field.hint}
												maxLength={200}
												placeholder="Optional hint for the extractor"
												onChange={(event) => updateField(typeIndex, fieldIndex, { hint: event.target.value })}
											/>
											<button type="button" className="text-button subtle" onClick={() => removeField(typeIndex, fieldIndex)}>Remove</button>
										</div>
									))}
								</div>
							</article>
						))}
						<button type="button" className="wiki-format-add" onClick={addType} disabled={draft.types.length >= 40}>+ Add an entry type</button>
					</div>
					{error && <p className="form-error" role="alert">{error}</p>}
					<div className="dialog-actions">
						<Dialog.Close asChild>
							<button type="button" className="quiet-button">Cancel</button>
						</Dialog.Close>
						<button type="button" className="button button-primary" onClick={() => void save()} disabled={saving}>
							{saving ? "Saving…" : "Save format"}
						</button>
					</div>
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}
