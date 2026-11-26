'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, type Diagnostics, type StorageReport } from '@/lib/api';
import { isUnauthorized } from '@/lib/auth-redirect';

function formatBytes(value: number) {
	if (value < 1024) return `${value} B`;
	const units = ['KB', 'MB', 'GB', 'TB'];
	let size = value / 1024;
	let unit = 0;
	while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
	return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unit]}`;
}

function when(value: string) {
	return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function statusTone(value: string) {
	if (value.startsWith('ok') || value === 'running') return 'ok';
	return 'warn';
}

export default function DiagnosticsPage() {
	const [report, setReport] = useState<Diagnostics | null>(null);
	const [storage, setStorage] = useState<StorageReport | null>(null);
	const [storageNote, setStorageNote] = useState('');
	const [cleaning, setCleaning] = useState(false);
	const [error, setError] = useState('');
	const [loading, setLoading] = useState(true);

	async function load() {
		setLoading(true);
		setError('');
		try {
			const [nextReport, nextStorage] = await Promise.all([api.diagnostics(), api.storage()]);
			setReport(nextReport);
			setStorage(nextStorage);
		} catch (cause) {
			if (isUnauthorized(cause)) return;
			setError(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'Diagnostics could not be loaded.');
		} finally {
			setLoading(false);
		}
	}

	async function cleanup() {
		setCleaning(true);
		setStorageNote('');
		try {
			const result = await api.cleanupStorage();
			const total = result.stories_deleted + result.chapters_deleted + result.jobs_deleted;
			setStorageNote(total === 0 ? 'Nothing was past its retention window.' : `Removed ${result.stories_deleted} stories, ${result.chapters_deleted} chapters, and ${result.jobs_deleted} finished jobs.`);
			await load();
		} catch (cause) {
			if (isUnauthorized(cause)) return;
			setStorageNote(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'Cleanup failed.');
		} finally {
			setCleaning(false);
		}
	}

	// Initial load; the request is asynchronous.
	// eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
	useEffect(() => { void load(); }, []);

	const expired = storage ? storage.expired.stories + storage.expired.chapters + storage.expired.jobs : 0;

	return <main className="library-page">
		<header className="library-header">
			<div className="app-header-left">
				<Link className="wordmark" href="/dashboard"><span className="wordmark-icon">s</span>stillroom</Link>
				<nav className="product-nav" aria-label="Workspace"><Link href="/dashboard">Writing</Link><Link href="/editing">Editing</Link><Link href="/settings">Settings</Link><Link href="/diagnostics" aria-current="page">Diagnostics</Link></nav>
			</div>
			<div className="header-account"><Link className="quiet-button" href="/settings" aria-label="Back to settings">Back</Link></div>
		</header>
		<section className="general-settings-page diagnostics-page">
			<div className="eyebrow">SYSTEM HEALTH</div>
			<div className="diagnostics-heading"><div><h1>Diagnostics</h1><p className="general-settings-intro">What the database, queue, model, and backups look like right now. This page is read-only.</p></div><button className="quiet-button" onClick={() => void load()} disabled={loading}>{loading ? 'Checking…' : 'Refresh'}</button></div>
			{error && <div className="notice" role="alert">{error}</div>}
			{report && <>
				<p className="diagnostics-stamp">Checked {when(report.generated_at)} · slow SQL warning at {report.slow_query_ms} ms</p>
				<div className="diagnostics-grid">
					<section className="profile-settings-card diagnostic-card">
						<div className="eyebrow">DATABASE</div><h2>{report.database === 'ok' ? 'Healthy' : 'Needs attention'}</h2>
						<dl><div><dt>Database</dt><dd className={`diagnostic-status ${statusTone(report.database)}`}>{report.database}</dd></div>
							<div><dt>Size</dt><dd>{formatBytes(report.database_size_bytes)}</dd></div>
							<div><dt>pgvector</dt><dd>{report.pgvector}</dd></div>
							<div><dt>Schema</dt><dd className={`diagnostic-status ${statusTone(report.schema_status)}`}>{report.schema_status}</dd></div></dl>
					</section>
					<section className="profile-settings-card diagnostic-card">
						<div className="eyebrow">QUEUE</div><h2>{report.worker === 'running' ? 'Worker running' : 'Worker offline'}</h2>
						<dl><div><dt>Queued</dt><dd>{report.jobs.queued}</dd></div><div><dt>Running</dt><dd>{report.jobs.running}</dd></div><div><dt>Failed</dt><dd>{report.jobs.failed}</dd></div><div><dt>Dead</dt><dd>{report.jobs.dead}</dd></div><div><dt>Succeeded</dt><dd>{report.jobs.succeeded}</dd></div></dl>
						{report.worker !== 'running' && <p className="diagnostic-note">The queue is not being drained. Start the worker with <code>make worker</code>.</p>}
					</section>
					<section className="profile-settings-card diagnostic-card">
						<div className="eyebrow">MODEL</div><h2>{report.ai_provider}</h2>
						<dl><div><dt>Model</dt><dd>{report.ai_model}</dd></div><div><dt>Ollama</dt><dd className={`diagnostic-status ${statusTone(report.ollama)}`}>{report.ollama}</dd></div></dl>
						<p className="diagnostic-note">A message about a missing model means Ollama is running but does not have the embedding or chat model pulled.</p>
					</section>
					<section className="profile-settings-card diagnostic-card">
						<div className="eyebrow">BACKUP</div><h2>{report.last_backup ? 'Last dump found' : 'No dump found'}</h2>
						{report.last_backup ? <dl><div><dt>File</dt><dd className="diagnostic-filename">{report.last_backup.filename}</dd></div><div><dt>Size</dt><dd>{formatBytes(report.last_backup.size_bytes)}</dd></div><div><dt>Written</dt><dd>{when(report.last_backup.modified_at)}</dd></div></dl> : <p className="diagnostic-note">Run <code>./scripts/backup.sh</code> and keep the dump somewhere other than this machine.</p>}
						<p className="diagnostic-note">A dump existing is not proof it restores. Run the restore drill in <code>Docs/backups.md</code>.</p>
					</section>
				</div>
				<section className="profile-settings-card diagnostics-usage">
					<div className="eyebrow">AI USAGE · LAST 30 DAYS</div><h2>Calls and tokens</h2>
					{report.ai_usage_30d.length === 0 ? <p>No model calls in the last 30 days.</p> : <table className="usage-table"><thead><tr><th>Purpose</th><th>Calls</th><th>Input</th><th>Output</th><th>Est. cost</th></tr></thead><tbody>{report.ai_usage_30d.map((row) => <tr key={row.purpose}><td>{row.purpose.replaceAll('_', ' ')}</td><td>{row.calls.toLocaleString()}</td><td>{row.input_tokens.toLocaleString()}</td><td>{row.output_tokens.toLocaleString()}</td><td>${row.cost_estimate.toFixed(4)}</td></tr>)}</tbody></table>}
				</section>
				{storage && <section className="profile-settings-card diagnostics-storage" aria-live="polite">
					<div className="storage-heading"><div><div className="eyebrow">STORAGE AND RETENTION</div><h2>{formatBytes(storage.database_size_bytes)} in PostgreSQL</h2><p className="diagnostic-note">Table sizes are for the whole database. Counts are for your account.</p></div><button className="quiet-button" onClick={() => void cleanup()} disabled={cleaning || expired === 0}>{cleaning ? 'Cleaning…' : expired === 0 ? 'Nothing expired' : 'Clean up expired'}</button></div>
					<div className="storage-counts">
						<div><span>Stories</span><strong>{storage.counts.stories.toLocaleString()}</strong></div>
						<div><span>Chapters</span><strong>{storage.counts.chapters.toLocaleString()}</strong></div>
						<div><span>Chunks</span><strong>{storage.counts.chunks.toLocaleString()}</strong></div>
						<div><span>Revisions</span><strong>{storage.counts.revisions.toLocaleString()}</strong></div>
					</div>
					<div className="storage-columns">
						<div><h3>Largest tables</h3><table className="usage-table"><thead><tr><th>Table</th><th>Size</th></tr></thead><tbody>{storage.tables.map((table) => <tr key={table.name}><td><code>{table.name}</code></td><td>{formatBytes(table.size_bytes)}</td></tr>)}</tbody></table></div>
						<div><h3>Retention</h3><dl><div><dt>Trash</dt><dd>{storage.trash_retention_days} days</dd></div><div><dt>Finished jobs</dt><dd>{storage.finished_jobs_retention_days} days</dd></div><div><dt>Trashed stories</dt><dd>{storage.counts.trashed_stories.toLocaleString()}</dd></div><div><dt>Trashed chapters</dt><dd>{storage.counts.trashed_chapters.toLocaleString()}</dd></div></dl><p className="diagnostic-note">{expired === 0 ? 'Nothing is past a retention window.' : `${expired} item${expired === 1 ? '' : 's'} are past a retention window.`} Cleanup deletes only those rows. PostgreSQL reuses the space over time; this button does not run a blocking VACUUM.</p></div>
					</div>
					{storageNote && <p role="status" className="diagnostic-note">{storageNote}</p>}
				</section>}
			</>}
		</section>
	</main>;
}