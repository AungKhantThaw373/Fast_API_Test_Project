'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type ChangeEvent } from 'react';

import { api, type BackupDocument } from '@/lib/api';

type Format = 'docx' | 'epub' | 'pdf' | 'markdown';

const FORMATS: { value: Format; name: string; note: string }[] = [
	{ value: 'docx', name: 'Word', note: '12 pt serif, double-spaced, indented, page numbers' },
	{ value: 'epub', name: 'EPUB', note: 'Reflowable e-reader book with chapter breaks' },
	{ value: 'pdf', name: 'PDF', note: 'Print-ready letter pages with a title page' },
	{ value: 'markdown', name: 'Markdown', note: 'Plain text manuscript plus the wiki appendix' },
];

function saveBlob(blob: Blob, filename: string) {
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement('a');
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportPanel({
	storyId,
	title,
	onClose,
	onPrepare,
}: {
	storyId: string;
	title: string;
	onClose: () => void;
	onPrepare: () => Promise<void>;
}) {
	const router = useRouter();
	const fileRef = useRef<HTMLInputElement>(null);
	const [format, setFormat] = useState<Format>('docx');
	const [includeWiki, setIncludeWiki] = useState(true);
	const [busy, setBusy] = useState<'export' | 'backup' | 'restore' | null>(null);
	const [message, setMessage] = useState('');
	const [error, setError] = useState('');

	useEffect(() => {
		function onKey(event: KeyboardEvent) {
			if (event.key === 'Escape') onClose();
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, [onClose]);

	async function exportFile() {
		setBusy('export');
		setError('');
		setMessage('');
		try {
			await onPrepare();
			const { blob, filename } = await api.exportStory(storyId, format, includeWiki);
			saveBlob(blob, filename);
			setMessage(`${format.toUpperCase()} is ready.`);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'That export could not be prepared.');
		} finally {
			setBusy(null);
		}
	}

	async function exportBackup() {
		setBusy('backup');
		setError('');
		setMessage('');
		try {
			await onPrepare();
			const document = await api.exportBackup(storyId);
			const safe = title.replace(/[\\/:*?"<>|]+/g, '-').trim() || 'story';
			saveBlob(new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' }), `${safe}-backup.json`);
			setMessage('Backup downloaded. Keep it somewhere outside this machine.');
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'That backup could not be prepared.');
		} finally {
			setBusy(null);
		}
	}

	async function restoreBackup(event: ChangeEvent<HTMLInputElement>) {
		const file = event.target.files?.[0];
		if (!file) return;
		setBusy('restore');
		setError('');
		setMessage('');
		try {
			const document = JSON.parse(await file.text()) as BackupDocument;
			if (!document || typeof document !== 'object' || !('format_version' in document)) {
				throw new Error('That file is not a Stillroom backup.');
			}
			const result = await api.importBackup(document);
			setMessage(`Restored as a new story: ${result.chapters} chapters, ${result.entities} entities.`);
			setTimeout(() => router.push(`/stories/${result.story_id}`), 900);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'That backup could not be restored.');
		} finally {
			event.target.value = '';
			setBusy(null);
		}
	}

	return (
		<div className="export-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
			<div className="export-panel" role="dialog" aria-modal="true" aria-labelledby="export-title">
				<header>
					<div><div className="eyebrow">LEAVE THE ROOM</div><h2 id="export-title">Export</h2></div>
					<button className="export-close" onClick={onClose} aria-label="Close export panel">×</button>
				</header>
				<p className="export-intro">The manuscript is saved first. Formatting follows the house style; nothing here edits the text.</p>

				<fieldset className="export-formats">
					<legend>Manuscript file</legend>
					{FORMATS.map((item) => (
						<label key={item.value} className={`export-format${format === item.value ? ' is-selected' : ''}`}>
							<input type="radio" name="export-format" value={item.value} checked={format === item.value} onChange={() => setFormat(item.value)} />
							<span><strong>{item.name}</strong><small>{item.note}</small></span>
						</label>
					))}
				</fieldset>
				<label className="export-check"><input type="checkbox" checked={includeWiki} onChange={(event) => setIncludeWiki(event.target.checked)} /> Include the story wiki appendix</label>
				<button className="button button-approve export-action" onClick={() => void exportFile()} disabled={busy !== null}>
					{busy === 'export' ? 'Preparing…' : `Download ${FORMATS.find((item) => item.value === format)?.name}`}
				</button>

				<hr />
				<section className="export-backup">
					<h3>Whole-story backup</h3>
					<p>Chapters, revisions, entities, facts, relationships, threads, events, arcs, and settings in one JSON file. Restoring always makes a new story; it never overwrites this one.</p>
					<div className="export-backup-actions">
						<button className="quiet-button" onClick={() => void exportBackup()} disabled={busy !== null}>{busy === 'backup' ? 'Packing…' : 'Download JSON backup'}</button>
						<button className="quiet-button" onClick={() => fileRef.current?.click()} disabled={busy !== null}>{busy === 'restore' ? 'Restoring…' : 'Restore from backup'}</button>
						<input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(event) => void restoreBackup(event)} />
					</div>
				</section>
				{message && <p className="export-message" role="status">{message}</p>}
				{error && <p className="export-error" role="alert">{error}</p>}
			</div>
		</div>
	);
}