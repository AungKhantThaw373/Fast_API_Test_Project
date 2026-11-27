"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";

import { useEntitySearch } from "@/components/wiki/use-wiki";
import { ENTITY_TYPE_LABELS, ENTITY_TYPES, entityTypeLabel } from "@/components/wiki/wiki-filters";
import { api, type EntityType, type StoryDetails, type WikiEntity } from "@/lib/api";

export type CaptureMode = "entity" | "fact" | "thread";

export interface CaptureSelection {
	mode: CaptureMode;
	text: string;
	line: number;
}

/**
 * One dialog for the three things a writer wants from a selection: make an entry,
 * record a fact, or open a thread. The quote and line are already filled in.
 */
export function CaptureDialog({
	storyId,
	story,
	chapterId,
	chapterNumber,
	selection,
	onClose,
	onDone,
}: {
	storyId: string;
	story: StoryDetails | undefined;
	chapterId: string;
	chapterNumber: number;
	selection: CaptureSelection;
	onClose: () => void;
	onDone: (entity?: WikiEntity) => void;
}) {
	const quoted = selection.text.trim();
	const [mode, setMode] = useState<CaptureMode>(selection.mode);
	const [name, setName] = useState(guessName(quoted));
	const [entityType, setEntityType] = useState<EntityType>("character");
	const [title, setTitle] = useState(quoted.length > 120 ? `${quoted.slice(0, 117)}…` : quoted);
	const [predicate, setPredicate] = useState("");
	const [value, setValue] = useState("");
	const [entityId, setEntityId] = useState("");
	const [searchTerm, setSearchTerm] = useState("");
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState("");

	const search = useEntitySearch(storyId, mode === "fact" ? searchTerm : "");
	const suggestions = (search.data ?? []).slice(0, 6);

	async function submit(event: React.FormEvent) {
		event.preventDefault();
		setBusy(true);
		setError("");
		try {
			if (mode === "entity") {
				const created = await api.createEntity(storyId, {
					name: name.trim(),
					entity_type: entityType,
					summary: quoted,
				});
				try {
					await api.createFact(created.id, {
						predicate: "summary",
						value_text: quoted,
						chapter_id: chapterId,
						quote: quoted,
						line_start: selection.line,
						status: "accepted",
					});
				} catch {
					// The entry is the point; the quote can be added later.
				}
				onDone(created);
				return;
			}
			if (mode === "fact") {
				if (!entityId) {
					setError("Choose the entry this fact belongs to.");
					setBusy(false);
					return;
				}
				if (!predicate.trim() || !value.trim()) {
					setError("A fact needs a name and a value.");
					setBusy(false);
					return;
				}
				await api.createFact(entityId, {
					predicate: predicate.trim(),
					value_text: value.trim(),
					chapter_id: chapterId,
					quote: quoted,
					line_start: selection.line,
					valid_from_chapter: chapterNumber,
					status: "accepted",
				});
				onDone();
				return;
			}
			if (!title.trim()) {
				setError("A thread needs a question or promise.");
				setBusy(false);
				return;
			}
			await api.createThread(storyId, {
				title: title.trim(),
				description: quoted,
				setup_chapter_id: chapterId,
				setup_quote: quoted,
				state: "open",
			});
			onDone();
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : "Could not save that.");
		} finally {
			setBusy(false);
		}
	}

	return (
		<Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card" aria-describedby="capture-hint">
					<Dialog.Title className="dialog-title">
						{mode === "entity" ? "New entry from this passage" : mode === "fact" ? "New fact from this passage" : "New thread from this passage"}
					</Dialog.Title>
					<Dialog.Description id="capture-hint" className="dialog-hint">
						Chapter {chapterNumber}, line {selection.line}. The quote is already attached.
					</Dialog.Description>

					<div className="capture-tabs" role="tablist" aria-label="What to capture">
						{(["entity", "fact", "thread"] as CaptureMode[]).map((option) => (
							<button
								key={option}
								role="tab"
								aria-selected={mode === option}
								className={mode === option ? "active" : ""}
								onClick={() => setMode(option)}
							>
								{option === "entity" ? "Entry" : option === "fact" ? "Fact" : "Thread"}
							</button>
						))}
					</div>

					<div className="wiki-capture-note">
						<strong>Captured</strong>
						<blockquote>“{quoted}”</blockquote>
					</div>

					<form className="wiki-form" onSubmit={submit}>
						{mode === "entity" && (
							<>
								<label>
									<span>Name</span>
									<input autoFocus value={name} onChange={(event) => setName(event.target.value)} maxLength={200} />
								</label>
								<label>
									<span>Type</span>
									<select value={entityType} onChange={(event) => setEntityType(event.target.value as EntityType)}>
										{ENTITY_TYPES.map((type) => (
											<option key={type} value={type}>
												{ENTITY_TYPE_LABELS[type]}
											</option>
										))}
									</select>
								</label>
							</>
						)}

						{mode === "fact" && (
							<>
								<label>
									<span>Entry</span>
									<input
										type="search"
										value={searchTerm}
										onChange={(event) => {
											setEntityId("");
											setSearchTerm(event.target.value);
										}}
										placeholder="Search the wiki…"
									/>
								</label>
								{entityId && <p className="capture-chosen">Fact will be attached to the chosen entry.</p>}
								{suggestions.length > 0 && !entityId && (
									<ul className="capture-suggestions">
										{suggestions.map((entity) => (
											<li key={entity.id}>
												<button
													type="button"
													onClick={() => {
														setEntityId(entity.id);
														setSearchTerm(entity.name);
													}}
												>
													<strong>{entity.name}</strong>
													<span>{entityTypeLabel(entity.entity_type)}</span>
												</button>
											</li>
										))}
									</ul>
								)}
								<label>
									<span>Fact</span>
									<input value={predicate} onChange={(event) => setPredicate(event.target.value)} placeholder="eye colour" />
								</label>
								<label>
									<span>Value</span>
									<input value={value} onChange={(event) => setValue(event.target.value)} placeholder="grey" />
								</label>
							</>
						)}

						{mode === "thread" && (
							<label>
								<span>Question or promise</span>
								<input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} maxLength={300} />
							</label>
						)}

						{error && <p className="form-error" role="alert">{error}</p>}
						<div className="dialog-actions">
							<Dialog.Close asChild>
								<button type="button" className="quiet-button">Cancel</button>
							</Dialog.Close>
							<button className="button button-primary" type="submit" disabled={busy}>
								{busy ? "Saving…" : mode === "entity" ? "Add entry" : mode === "fact" ? "Save fact" : "Open thread"}
							</button>
						</div>
					</form>
					<p className="wiki-quiet">Story: {story?.title ?? "…"}</p>
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}

/** A capitalised phrase is a better default name than the whole sentence. */
export function guessName(text: string): string {
	const match = text.match(/\b([A-Z][a-zA-Z'’\-]+(?:\s+[A-Z][a-zA-Z'’\-]+){0,2})\b/);
	const candidate = (match?.[1] ?? text).trim();
	return candidate.length > 60 ? `${candidate.slice(0, 59)}…` : candidate;
}
