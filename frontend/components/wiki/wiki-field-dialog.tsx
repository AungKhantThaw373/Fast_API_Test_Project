"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";

import type { WikiFieldDefinition } from "@/lib/api";

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

/** Add or rename one custom field without leaving the entry page. Values live
 * in facts under the field key, so the key is fixed when editing. */
export function WikiFieldDialog({
	field,
	existingKeys,
	onSave,
	onClose,
}: {
	field?: WikiFieldDefinition;
	existingKeys: string[];
	onSave: (field: WikiFieldDefinition) => Promise<void>;
	onClose: () => void;
}) {
	const [label, setLabel] = useState(field?.label ?? "");
	const [hint, setHint] = useState(field?.hint ?? "");
	const [key, setKey] = useState(() => field?.key ?? uniqueKey("field", existingKeys));
	const [keyTouched, setKeyTouched] = useState(Boolean(field));
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState("");

	function changeLabel(value: string) {
		setLabel(value);
		if (!field && !keyTouched) setKey(uniqueKey(slugKey(value), existingKeys));
	}

	async function submit() {
		const cleanLabel = label.trim();
		const cleanKey = key.trim();
		if (!cleanLabel) {
			setError("Give the field a name.");
			return;
		}
		if (!/^[a-z][a-z0-9_]{0,31}$/.test(cleanKey)) {
			setError("The key starts with a letter and uses lowercase letters, numbers, or underscores.");
			return;
		}
		setSaving(true);
		setError("");
		try {
			await onSave({ key: cleanKey, label: cleanLabel, hint: hint.trim() });
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : "That field could not be saved.");
			setSaving(false);
		}
	}

	return (
		<Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card wiki-field-dialog" aria-describedby="wiki-field-hint">
					<Dialog.Title className="dialog-title">{field ? "Edit field" : "Add a field"}</Dialog.Title>
					<Dialog.Description id="wiki-field-hint" className="dialog-hint">
						Fields are short facts shown on this entry. They keep the same provenance and review status as any other fact.
					</Dialog.Description>
					<label className="wiki-format-description">
						<span>Name</span>
						<input autoFocus value={label} maxLength={80} placeholder="Hair colour" onChange={(event) => changeLabel(event.target.value)} />
					</label>
					<label className="wiki-format-description">
						<span>Hint <small>optional</small></span>
						<input value={hint} maxLength={160} placeholder="A short note for the extractor" onChange={(event) => setHint(event.target.value)} />
					</label>
					<label className="wiki-format-description">
						<span>Fact key <small>{field ? "fixed so existing values stay connected" : "lowercase, no spaces"}</small></span>
						<input value={key} maxLength={32} disabled={Boolean(field)} onChange={(event) => { setKeyTouched(true); setKey(event.target.value); }} />
					</label>
					{error && <p className="form-error" role="alert">{error}</p>}
					<div className="dialog-actions">
						<Dialog.Close asChild>
							<button type="button" className="quiet-button">Cancel</button>
						</Dialog.Close>
						<button type="button" className="button button-primary" onClick={() => void submit()} disabled={saving}>
							{saving ? "Saving…" : field ? "Save field" : "Add field"}
						</button>
					</div>
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}
