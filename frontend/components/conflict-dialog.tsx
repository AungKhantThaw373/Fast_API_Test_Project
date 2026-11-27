'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { useMemo, useState } from 'react';
import { compactDiff, lineDiff } from '@/lib/line-diff';

export type ConflictDialogProps = {
	open: boolean;
	localTitle: string;
	localContent: string;
	serverTitle: string;
	serverContent: string;
	serverRevision: number;
	onKeepMine: () => void;
	onReloadServer: () => void;
	onCopyChanges: () => void;
	busy?: boolean;
};

export function ConflictDialog({
	open,
	localTitle,
	localContent,
	serverTitle,
	serverContent,
	serverRevision,
	onKeepMine,
	onReloadServer,
	onCopyChanges,
	busy = false,
}: ConflictDialogProps) {
	const [view, setView] = useState<'diff' | 'side-by-side'>('diff');
	const diff = useMemo(() => compactDiff(lineDiff(serverContent, localContent)), [serverContent, localContent]);

	return (
		<Dialog.Root open={open}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card conflict-card" aria-describedby="conflict-description">
					<Dialog.Title className="dialog-title">This chapter changed somewhere else</Dialog.Title>
					<Dialog.Description className="dialog-description" id="conflict-description">
						Another tab or device saved this chapter (version {serverRevision}) while you were writing.
						Choose what to keep. Nothing is overwritten until you decide.
					</Dialog.Description>

					<div className="conflict-tabs" role="tablist" aria-label="Compare versions">
						<button role="tab" aria-selected={view === 'diff'} className={view === 'diff' ? 'active' : ''} onClick={() => setView('diff')}>Line changes</button>
						<button role="tab" aria-selected={view === 'side-by-side'} className={view === 'side-by-side' ? 'active' : ''} onClick={() => setView('side-by-side')}>Side by side</button>
					</div>

					{view === 'diff' ? (
						<div className="conflict-diff" aria-label="Differences between the saved version and your version">
							{diff.length ? diff.map((line, index) => (
								<div key={index} className={`diff-line diff-${line.kind}`}>
									<span className="diff-gutter">{line.kind === 'added' ? '+' : line.kind === 'removed' ? '−' : ' '}</span>
									<span className="diff-text">{line.text || '\u00a0'}</span>
								</div>
							)) : <p className="pane-empty">The two versions differ only in whitespace.</p>}
						</div>
					) : (
						<div className="conflict-columns">
							<section>
								<h3>Saved version</h3>
								<p className="conflict-title">{serverTitle}</p>
								<pre>{serverContent}</pre>
							</section>
							<section>
								<h3>Your version</h3>
								<p className="conflict-title">{localTitle}</p>
								<pre>{localContent}</pre>
							</section>
						</div>
					)}

					<div className="dialog-actions conflict-actions">
						<button className="button button-primary" disabled={busy} onClick={onKeepMine}>Keep mine</button>
						<button className="quiet-button" disabled={busy} onClick={onReloadServer}>Reload saved version</button>
						<button className="quiet-button" disabled={busy} onClick={onCopyChanges}>Copy changes and merge</button>
					</div>
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}
