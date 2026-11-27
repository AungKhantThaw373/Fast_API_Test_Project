"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMemo, useState } from "react";

import type { EntityFact, FactStatus, FactValueType, StoryDetails } from "@/lib/api";

export interface FactDraft {
	predicate: string;
	value: string;
	valueType: FactValueType;
	chapterId: string;
	lineStart: string;
	quote: string;
	confidence: number;
	status: FactStatus;
	validFrom: string;
	validTo: string;
}

export function draftFromFact(fact: EntityFact, fallbackChapterId: string): FactDraft {
	return {
		predicate: fact.predicate,
		value: fact.value_text ?? (fact.value_number !== null ? String(fact.value_number) : fact.value_date ?? ""),
		valueType: fact.value_type,
		chapterId: fact.chapter_id ?? fallbackChapterId,
		lineStart: fact.line_start ? String(fact.line_start) : "",
		quote: fact.quote ?? "",
		confidence: fact.confidence,
		status: fact.status,
		validFrom: fact.valid_from_chapter ? String(fact.valid_from_chapter) : "",
		validTo: fact.valid_to_chapter ? String(fact.valid_to_chapter) : "",
	};
}

export const EMPTY_FACT: FactDraft = {
	predicate: "",
	value: "",
	valueType: "text",
	chapterId: "",
	lineStart: "",
	quote: "",
	confidence: 70,
	status: "accepted",
	validFrom: "",
	validTo: "",
};

export function FactDialog({
	story,
	entityName,
	initial,
	suggestions: existingSuggestions = [],
	onClose,
	onSave,
}: {
	story: StoryDetails | undefined;
	entityName: string;
	initial: FactDraft;
	suggestions?: string[];
	onClose: () => void;
	onSave: (draft: FactDraft) => Promise<void>;
}) {
	const [draft, setDraft] = useState<FactDraft>(initial);
	const [showMore, setShowMore] = useState(false);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState("");

	const chapters = useMemo(() => story?.chapters ?? [], [story]);
	const suggestions = useMemo(() => {
		const predicates = new Set([
			"summary",
			"eye_color",
			"age",
			"rank",
			"location",
			"goal",
			"secret",
			...existingSuggestions,
		]);
		return [...predicates].sort((a, b) => a.localeCompare(b));
	}, [existingSuggestions]);

	async function submit(event: React.FormEvent) {
		event.preventDefault();
		if (!draft.predicate.trim()) {
			setError("Name the fact, for example “eye colour”.");
			return;
		}
		if (!draft.value.trim()) {
			setError("A fact needs a value.");
			return;
		}
		if (!draft.chapterId) {
			setError("Choose the chapter this comes from.");
			return;
		}
		setSaving(true);
		setError("");
		try {
			await onSave(draft);
			onClose();
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : "Could not save that fact.");
		} finally {
			setSaving(false);
		}
	}

	return (
		<Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card" aria-describedby="fact-hint">
					<Dialog.Title className="dialog-title">A fact about {entityName}</Dialog.Title>
					<Dialog.Description id="fact-hint" className="dialog-hint">
						Every fact needs the chapter it came from. A quote makes it checkable.
					</Dialog.Description>
					<form className="wiki-form" onSubmit={submit}>
						<label>
							<span>Fact</span>
							<input
								list="fact-predicate-suggestions"
								value={draft.predicate}
								onChange={(event) => setDraft({ ...draft, predicate: event.target.value })}
								placeholder="eye colour"
								maxLength={100}
								autoFocus
							/>
							<datalist id="fact-predicate-suggestions">
								{suggestions.map((value) => (
									<option key={value} value={value} />
								))}
							</datalist>
							<small>Use any field this novel needs. Existing fields appear as suggestions.</small>
						</label>
						<label>
							<span>Value</span>
							<input
								value={draft.value}
								onChange={(event) => setDraft({ ...draft, value: event.target.value })}
								placeholder="grey"
							/>
						</label>
						<label>
							<span>Chapter</span>
							<select value={draft.chapterId} onChange={(event) => setDraft({ ...draft, chapterId: event.target.value })}>
								<option value="">Choose a chapter…</option>
								{chapters.map((chapter) => (
									<option key={chapter.id} value={chapter.id}>
										{chapter.chapter_number}. {chapter.title}
									</option>
								))}
							</select>
						</label>
						<label>
							<span>Quote</span>
							<textarea
								rows={2}
								value={draft.quote}
								onChange={(event) => setDraft({ ...draft, quote: event.target.value })}
								placeholder="The sentence that proves it."
							/>
						</label>
						<button type="button" className="text-button subtle" onClick={() => setShowMore((value) => !value)}>
							{showMore ? "Fewer options" : "More options"}
						</button>
						{showMore && (
							<div className="wiki-form-grid">
								<label>
									<span>Value type</span>
									<select
										value={draft.valueType}
										onChange={(event) => setDraft({ ...draft, valueType: event.target.value as FactValueType })}
									>
										<option value="text">Text</option>
										<option value="number">Number</option>
										<option value="date">Date</option>
										<option value="boolean">True / false</option>
									</select>
								</label>
								<label>
									<span>Status</span>
									<select
										value={draft.status}
										onChange={(event) => setDraft({ ...draft, status: event.target.value as FactStatus })}
									>
										<option value="accepted">Accepted</option>
										<option value="proposed">Proposed</option>
										<option value="rejected">Rejected</option>
									</select>
								</label>
								<label>
									<span>Line</span>
									<input
										inputMode="numeric"
										value={draft.lineStart}
										onChange={(event) => setDraft({ ...draft, lineStart: event.target.value.replace(/\D/g, "") })}
										placeholder="48"
									/>
								</label>
								<label>
									<span>Confidence</span>
									<input
										type="number"
										min={0}
										max={100}
										value={draft.confidence}
										onChange={(event) => setDraft({ ...draft, confidence: Number(event.target.value) })}
									/>
								</label>
								<label>
									<span>Valid from chapter</span>
									<input
										inputMode="numeric"
										value={draft.validFrom}
										onChange={(event) => setDraft({ ...draft, validFrom: event.target.value.replace(/\D/g, "") })}
										placeholder="12"
									/>
								</label>
								<label>
									<span>Valid to chapter</span>
									<input
										inputMode="numeric"
										value={draft.validTo}
										onChange={(event) => setDraft({ ...draft, validTo: event.target.value.replace(/\D/g, "") })}
										placeholder="—"
									/>
								</label>
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
								{saving ? "Saving…" : "Save fact"}
							</button>
						</div>
					</form>
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}
