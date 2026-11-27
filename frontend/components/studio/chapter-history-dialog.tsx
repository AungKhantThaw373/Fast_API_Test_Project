	'use client';

	import { useState } from 'react';
	import type { ChapterRevisionSummary, RevisionDiff } from '@/lib/api';

	type ChapterHistoryDialogProps = {
		canCheckpoint: boolean;
		history: ChapterRevisionSummary[];
		loading: boolean;
		diff: RevisionDiff | null;
		onClose: () => void;
		onSaveCheckpoint: () => void;
		onCompare: (first: number, second: number) => void;
		onRestore: (revision: ChapterRevisionSummary) => void;
		onHideDiff: () => void;
	};

	/** Presentational version history. The Studio still owns the data and actions. */
	export function ChapterHistoryDialog({
		canCheckpoint,
		history,
		loading,
		diff,
		onClose,
		onSaveCheckpoint,
		onCompare,
		onRestore,
		onHideDiff,
	}: ChapterHistoryDialogProps) {
		const [selection, setSelection] = useState<number[]>([]);

		return (
			<div className="history-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
				<section className="history-dialog" role="dialog" aria-modal="true" aria-label="Chapter version history">
					<header>
						<div><div className="eyebrow">DRAFT SAFETY</div><h2>Version history</h2><p>Pin a checkpoint before a big rewrite. Select two versions to compare them.</p></div>
						<button className="quiet-button" onClick={onClose}>Close</button>
					</header>
					<div className="history-actions">
						<button className="button button-approve" disabled={!canCheckpoint} onClick={onSaveCheckpoint}>Save checkpoint</button>
						{selection.length === 2 && <button className="quiet-button" onClick={() => onCompare(selection[0], selection[1])}>Compare selected</button>}
					</div>
					{loading ? <div className="pane-empty">Loading saved versions…</div> : history.length ? (
						<div className="history-list">
							{history.map((revision) => (
								<article key={revision.revision_number} className={selection.includes(revision.revision_number) ? 'selected' : ''}>
									<div>
										<strong>Version {revision.revision_number} <span className={'history-kind kind-' + revision.kind}>{revision.kind}</span></strong>
										<span>{revision.title} · {revision.word_count.toLocaleString()} words</span>
										<time>{new Date(revision.created_at).toLocaleString()}</time>
									</div>
									<div className="history-row-actions">
										<label className="history-pick">
											<input
												type="checkbox"
												checked={selection.includes(revision.revision_number)}
												onChange={() => setSelection((current) => current.includes(revision.revision_number) ? current.filter((value) => value !== revision.revision_number) : [...current, revision.revision_number].slice(-2))}
												aria-label={`Select version ${revision.revision_number} for comparison`}
											/>
											<span>Compare</span>
										</label>
										<button className="button button-approve" onClick={() => onRestore(revision)}>Restore</button>
									</div>
								</article>
							))}
						</div>
					) : <div className="pane-empty">Older versions appear here after the chapter is edited.</div>}
					{diff && <section className="history-diff" aria-label="Version differences">
						<header><strong>Versions {diff.older.revision_number} → {diff.newer.revision_number}</strong><button className="text-button" onClick={onHideDiff}>Hide</button></header>
						{diff.hunks.length ? diff.hunks.map((hunk, index) => (
							<div className="diff-hunk" key={index}>
								<div className="diff-hunk-head">@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@</div>
								{hunk.lines.map((line, lineIndex) => {
									const kind = line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : 'same';
									return <div key={lineIndex} className={'diff-line diff-' + kind}><span className="diff-gutter">{line.slice(0, 1)}</span><span className="diff-text">{line.slice(1) || ' '}</span></div>;
								})}
							</div>
						)) : <p className="pane-empty">No line changes between those versions.</p>}
					</section>}
				</section>
			</div>
		);
	}