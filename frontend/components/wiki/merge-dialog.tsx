"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";

import { useEntitySearch } from "@/components/wiki/use-wiki";
import { useStoryWikiFormat } from "@/components/wiki/wiki-format-context";
import { entityTypeLabel } from "@/components/wiki/wiki-filters";
import { api, type WikiEntity } from "@/lib/api";

export function MergeDialog({
	storyId,
	entity,
	onClose,
	onMerged,
}: {
	storyId: string;
	entity: WikiEntity;
	onClose: () => void;
	onMerged: (target: WikiEntity) => void;
}) {
	const format = useStoryWikiFormat();
	const [term, setTerm] = useState("");
	const [target, setTarget] = useState<WikiEntity | null>(null);
	const [preview, setPreview] = useState<Record<string, number> | null>(null);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState("");
	const search = useEntitySearch(storyId, term);

	const candidates = (search.data ?? []).filter((row) => row.id !== entity.id);

	async function choose(candidate: WikiEntity) {
		setTarget(candidate);
		setError("");
		setBusy(true);
		try {
			const result = await api.mergeEntity(entity.id, candidate.id, true);
			setPreview(result.moved);
		} catch (cause) {
			setPreview(null);
			setError(cause instanceof Error ? cause.message : "Could not preview that merge.");
		} finally {
			setBusy(false);
		}
	}

	async function confirm() {
		if (!target) return;
		setBusy(true);
		setError("");
		try {
			await api.mergeEntity(entity.id, target.id);
			onMerged(target);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : "Could not merge those entries.");
		} finally {
			setBusy(false);
		}
	}

	return (
		<Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card" aria-describedby="merge-hint">
					<Dialog.Title className="dialog-title">Merge “{entity.name}” into…</Dialog.Title>
					<Dialog.Description id="merge-hint" className="dialog-hint">
						Facts, mentions, relationships, and threads move to the target. Nothing is deleted, and the
						merge can be undone.
					</Dialog.Description>

					<label className="wiki-form">
						<span className="wiki-form-label">Search for the entry to keep</span>
						<input
							autoFocus
							type="search"
							value={term}
							onChange={(event) => setTerm(event.target.value)}
							placeholder="Start typing a name"
						/>
					</label>

					<ul className="merge-candidates">
						{candidates.map((candidate) => (
							<li key={candidate.id}>
								<button
									className={`merge-candidate${target?.id === candidate.id ? " selected" : ""}`}
									onClick={() => void choose(candidate)}
								>
									<strong>{candidate.name}</strong>
									<span>{entityTypeLabel(candidate.entity_type, format)}</span>
									{candidate.summary && <small>{candidate.summary.slice(0, 90)}</small>}
								</button>
							</li>
						))}
						{term.trim() && !candidates.length && !search.isPending && (
							<li className="wiki-quiet">No other entry matches “{term}”.</li>
						)}
					</ul>

					{target && (
						<div className="merge-preview" role="status" aria-live="polite">
							<strong>
								{entity.name} → {target.name}
							</strong>
							{preview ? (
								<ul>
									<li>{preview.facts ?? 0} facts</li>
									<li>{preview.mentions ?? 0} mentions</li>
									<li>{preview.relationships ?? 0} relationships</li>
									<li>{preview.threads ?? 0} threads</li>
									<li>{preview.events ?? 0} events</li>
									<li>{preview.aliases ?? 0} aliases</li>
								</ul>
							) : (
								<p className="wiki-quiet">{busy ? "Counting what would move…" : "No preview yet."}</p>
							)}
							{(preview?.facts ?? 0) > 0 && (
								<p className="merge-conflict-note">
									Both entries may describe the same fact. After merging, the fact list will show any
									disagreement so you can choose.
								</p>
							)}
						</div>
					)}

					{error && <p className="form-error" role="alert">{error}</p>}
					<div className="dialog-actions">
						<Dialog.Close asChild>
							<button type="button" className="quiet-button">Cancel</button>
						</Dialog.Close>
						<button className="button button-primary" disabled={!target || busy || !preview} onClick={() => void confirm()}>
							{busy ? "Working…" : "Merge entries"}
						</button>
					</div>
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}
