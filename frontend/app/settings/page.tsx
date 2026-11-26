'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { api, type AuditEvent, type AuthSession, type CurrentUser } from '@/lib/api';
import { isUnauthorized } from '@/lib/auth-redirect';
import { AIProviderSettingsForm } from '@/components/ai-provider-settings';
import { AppShell } from '@/components/app-shell';

function deviceName(userAgent: string) {
	if (!userAgent) return 'Unknown device';
	if (/iphone|ipad|android/i.test(userAgent)) return 'Phone or tablet';
	if (/edg\//i.test(userAgent)) return 'Microsoft Edge';
	if (/chrome\//i.test(userAgent)) return 'Chrome';
	if (/firefox\//i.test(userAgent)) return 'Firefox';
	if (/safari\//i.test(userAgent)) return 'Safari';
	return userAgent.slice(0, 80);
}

function shortDate(value: string) {
	return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

const ACTION_LABELS: Record<string, string> = {
	data_export: 'Exported all account data',
	account_deleted: 'Deleted the account',
	password_changed: 'Changed the password',
	password_reset_requested: 'Requested a password reset',
	password_reset: 'Reset the password',
	provider_changed: 'Changed the AI provider',
	provider_reset: 'Reset the AI provider',
	story_trashed: 'Moved a story to the trash',
	story_deleted: 'Permanently deleted a story',
	chapter_trashed: 'Moved a chapter to the trash',
	chapter_deleted: 'Permanently deleted a chapter',
	entity_merged: 'Merged two wiki entries',
	entity_unmerged: 'Undid a wiki merge',
	story_exported: 'Exported a manuscript',
	story_backup_exported: 'Downloaded a story backup',
	story_backup_imported: 'Restored a story backup',
};

export default function GeneralSettingsPage() {
	const router = useRouter();
	const [user, setUser] = useState<CurrentUser | null>(null);
	const [sessions, setSessions] = useState<AuthSession[]>([]);
	const [audit, setAudit] = useState<AuditEvent[]>([]);
	const [loading, setLoading] = useState(true);
	const [currentPassword, setCurrentPassword] = useState('');
	const [newPassword, setNewPassword] = useState('');
	const [confirmPassword, setConfirmPassword] = useState('');
	const [accountError, setAccountError] = useState('');
	const [accountNotice, setAccountNotice] = useState('');
	const [busy, setBusy] = useState(false);
	const [deletePassword, setDeletePassword] = useState('');
	const [deleteConfirmation, setDeleteConfirmation] = useState('');
	const [deleteError, setDeleteError] = useState('');
	const [deleting, setDeleting] = useState(false);

	useEffect(() => {
		let active = true;
		api.me().then((account) => { if (active) setUser(account); }).catch((cause: unknown) => {
			if (!active) return;
			if (isUnauthorized(cause)) return;
		}).finally(() => { if (active) setLoading(false); });
		api.sessions().then((rows) => { if (active) setSessions(rows); }).catch(() => undefined);
		api.auditEvents().then((rows) => { if (active) setAudit(rows); }).catch(() => undefined);
		return () => { active = false; };
	}, [router]);

	async function changePassword(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setAccountError('');
		setAccountNotice('');
		if (newPassword !== confirmPassword) {
			setAccountError('The two new passwords do not match.');
			return;
		}
		setBusy(true);
		try {
			await api.changePassword(currentPassword, newPassword);
			router.replace('/login?reset=done');
		} catch (cause) {
			setAccountError(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'The password could not be changed.');
		} finally {
			setBusy(false);
		}
	}

	async function revoke(session: AuthSession) {
		setAccountError('');
		try {
			await api.revokeSession(session.id);
			if (session.current) {
				router.replace('/login');
				return;
			}
			setSessions(await api.sessions());
			setAccountNotice('That device has been signed out.');
		} catch (cause) {
			setAccountError(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'The device could not be signed out.');
		}
	}

	async function deleteAccount(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setDeleteError('');
		setDeleting(true);
		try {
			await api.deleteAccount(deletePassword, deleteConfirmation);
			router.replace('/login?deleted=done');
		} catch (cause) {
			setDeleteError(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'The account could not be deleted.');
		} finally {
			setDeleting(false);
		}
	}

	async function revokeEverywhere() {
		setAccountError('');
		try {
			await api.revokeAllSessions();
			router.replace('/login');
		} catch (cause) {
			setAccountError(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'Sessions could not be signed out.');
		}
	}

	if (loading) return <main className="quiet-loading"><span className="loading-mark" /><p>Opening settings…</p></main>;

	return <AppShell active="settings" user={user?.username}>
		<section className="general-settings-page">
			<h1>Settings</h1>
			<p className="general-settings-intro">Your account, sessions, and website preferences.</p>
			<div className="general-settings-layout">
				<nav className="general-settings-nav" aria-label="Settings sections"><span className="selected">Profile</span><a href="#ai">AI</a><a href="#password">Password</a><a href="#sessions">Sessions</a><a href="#your-data">Data</a><a href="#activity">Activity</a><a href="#privacy">Privacy</a></nav>
				<div className="general-settings-main">
					<section className="profile-settings-card"><div className="eyebrow">PROFILE</div><h2>Account details</h2><dl><div><dt>Username</dt><dd>{user?.username ?? '—'}</dd></div><div><dt>Email</dt><dd>{user?.email ?? '—'}</dd></div></dl></section>
					<section className="profile-settings-card" id="ai"><AIProviderSettingsForm /></section>
					<section className="profile-settings-card" id="password">
						<div className="eyebrow">PASSWORD</div><h2>Change your password</h2>
						<p>Changing it signs out every device, including this one. You will sign in again with the new password.</p>
						<form className="account-form" onSubmit={changePassword}>
							<label>Current password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required autoComplete="current-password" /></label>
							<label>New password<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required minLength={10} autoComplete="new-password" /></label>
							<label>Confirm new password<input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength={10} autoComplete="new-password" /></label>
							{accountNotice && <p className="form-notice" role="status">{accountNotice}</p>}
							{accountError && <p className="form-error" role="alert">{accountError}</p>}
							<button className="button button-primary" disabled={busy}>{busy ? 'Changing…' : 'Change password'}</button>
						</form>
					</section>
					<section className="profile-settings-card" id="sessions">
						<div className="eyebrow">SESSIONS</div><h2>Where you are signed in</h2>
						<p>Each row is one browser session. Revoke anything you do not recognise.</p>
						<ul className="session-list">
							{sessions.map((session) => <li key={session.id} className="session-row">
								<div><strong>{deviceName(session.user_agent)} {session.current && <span className="session-current">This device</span>}</strong>
									<span>{session.ip || 'Unknown address'} · signed in {shortDate(session.created_at)} · last seen {shortDate(session.last_seen_at)}</span></div>
								<button className="quiet-button" onClick={() => void revoke(session)}>{session.current ? 'Sign out' : 'Revoke'}</button>
							</li>)}
						</ul>
						{sessions.length === 0 && <p>No active sessions were returned.</p>}
						<button className="quiet-button" onClick={() => void revokeEverywhere()}>Sign out everywhere</button>
					</section>
					<section className="profile-settings-card" id="your-data">
						<div className="eyebrow">YOUR DATA</div><h2>Take it with you</h2>
						<p>Download every story, chapter, wiki entry, draft file, and preference in one archive. It opens with any zip tool: a JSON data file, Markdown reading copies, and your original uploads. Provider API keys are never included.</p>
						<div className="data-actions"><a className="button button-primary" href={api.accountExportUrl} download>Export all my data (.zip)</a></div>
						<p className="data-retention">Deleted stories and chapters wait in the trash for 30 days. Deleting your account removes everything immediately, including that trash; the export above is the only copy you keep.</p>
					</section>
					<section className="profile-settings-card" id="activity">
						<div className="eyebrow">ACTIVITY</div><h2>Recent account changes</h2>
						<p>The last few sensitive actions on this account. Each entry keeps only a short description, an address, and a time; story prose is never written to this log.</p>
						<ul className="audit-list">
							{audit.map((event) => <li key={event.id} className="audit-row">
								<div><strong>{ACTION_LABELS[event.action] ?? event.action.replaceAll('_', ' ')}</strong>
									{typeof event.detail.title === 'string' && <span>{event.detail.title}</span>}
									<span>{shortDate(event.created_at)} · {event.ip || 'unknown address'}</span></div>
							</li>)}
						</ul>
						{audit.length === 0 && <p>No activity has been recorded yet.</p>}
					</section>
					<section className="profile-settings-card danger-card" id="delete-account">
						<div className="eyebrow">DANGER ZONE</div><h2>Delete this account</h2>
						<p>This deletes your account and every story, chapter, wiki entry, upload, session, and setting. It cannot be undone, and it is not limited to the trash. Export your data first if you want a copy.</p>
						<form className="account-form" onSubmit={deleteAccount}>
							<label>Type your username to confirm<input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} required autoComplete="off" placeholder={user?.username ?? 'username'} /></label>
							<label>Password<input type="password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} required autoComplete="current-password" /></label>
							{deleteError && <p className="form-error" role="alert">{deleteError}</p>}
							<button className="button danger-button" disabled={deleting}>{deleting ? 'Deleting…' : 'Delete my account and data'}</button>
						</form>
					</section>
					<section className="general-privacy" id="privacy"><div className="eyebrow">PRIVACY</div><h2>Your story data</h2><p>Your AI provider is configured in AI above. Each story’s analysis controls stay with that story. When analysis is enabled, chapter text and relevant earlier excerpts are sent to that provider. Local indexing stays on Ollama.</p><Link className="settings-writing-link" href="/dashboard">Go to Writing</Link></section>
				</div>
			</div>
		</section>
	</AppShell>;
}