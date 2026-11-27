'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { api, type AuditEvent, type AuthSession, type CurrentUser } from '@/lib/api';
import { isUnauthorized } from '@/lib/auth-redirect';
import { AIProviderSettingsForm } from '@/components/ai-provider-settings';
import { AppShell } from '@/components/app-shell';

type SettingsSection = 'profile' | 'ai' | 'security' | 'sessions' | 'data' | 'activity';

const SECTIONS: { id: SettingsSection; label: string; hint: string }[] = [
	{ id: 'profile', label: 'Profile', hint: 'Name and email' },
	{ id: 'ai', label: 'AI & API', hint: 'Provider, model, key' },
	{ id: 'security', label: 'Security', hint: 'Password' },
	{ id: 'sessions', label: 'Sessions', hint: 'Devices and sign-out' },
	{ id: 'data', label: 'Data & privacy', hint: 'Export and deletion' },
	{ id: 'activity', label: 'Activity', hint: 'Recent account events' },
];

function sectionFrom(value: string | null): SettingsSection {
	return SECTIONS.some((item) => item.id === value) ? (value as SettingsSection) : 'profile';
}

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

function SettingsPanel({
	id,
	eyebrow,
	title,
	description,
	children,
	danger = false,
}: {
	id: string;
	eyebrow: string;
	title: string;
	description: string;
	children: ReactNode;
	danger?: boolean;
}) {
	return (
		<section className={`settings-panel${danger ? ' settings-danger' : ''}`} id={id} aria-labelledby={`${id}-heading`}>
			<header className="settings-panel-head">
				<div className="eyebrow">{eyebrow}</div>
				<h2 id={`${id}-heading`}>{title}</h2>
				<p>{description}</p>
			</header>
			<div className="settings-panel-body">{children}</div>
		</section>
	);
}

export default function GeneralSettingsPage() {
	return (
		<Suspense fallback={<main className="quiet-loading"><span className="loading-mark" /><p>Opening settings…</p></main>}>
			<SettingsInner />
		</Suspense>
	);
}

function SettingsInner() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const storyParam = searchParams.get('story');
	const storyId = storyParam && /^[0-9a-f-]{36}$/i.test(storyParam) ? storyParam : null;
	const [section, setSection] = useState<SettingsSection>(() => sectionFrom(searchParams.get('section')));
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

	function chooseSection(next: SettingsSection) {
		setSection(next);
		const params = new URLSearchParams();
		params.set('section', next);
		if (storyId) params.set('story', storyId);
		router.replace(`/settings?${params.toString()}`, { scroll: false });
	}

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

	const backHref = storyId ? `/stories/${storyId}` : '/dashboard';
	const backLabel = storyId ? 'Back to the writing desk' : 'Back to the library';

	return <AppShell active="settings" user={user?.username}>
		<main className="settings-page">
			<header className="settings-head">
				<Link className="settings-back" href={backHref}>← {backLabel}</Link>
				<div className="eyebrow">YOUR WORKSPACE</div>
				<h1>Settings</h1>
				<p>Account, API connection, privacy, and the trail of changes. Choose a category on the left; the page keeps its place.</p>
			</header>
			<div className="settings-layout">
				<aside className="settings-nav" aria-label="Settings categories">
					<label className="settings-select-label">
						<span>Category</span>
						<select value={section} onChange={(event) => chooseSection(event.target.value as SettingsSection)}>
							{SECTIONS.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
						</select>
					</label>
					<nav className="settings-nav-list">
						{SECTIONS.map((item, index) => (
							<button key={item.id} type="button" aria-current={section === item.id ? 'page' : undefined} onClick={() => chooseSection(item.id)}>
								<span className="settings-nav-number">{String(index + 1).padStart(2, '0')}</span>
								<span><strong>{item.label}</strong><small>{item.hint}</small></span>
							</button>
						))}
					</nav>
				</aside>
				<div className="settings-content">
					{section === 'profile' && (
						<SettingsPanel id="profile" eyebrow="PROFILE" title="Account details" description="The name on your work and the address used to sign in.">
							<dl className="settings-facts">
								<div><dt>Username</dt><dd>{user?.username ?? '—'}</dd></div>
								<div><dt>Email</dt><dd>{user?.email ?? '—'}</dd></div>
							</dl>
							<p className="settings-note">To change either field, contact the workspace owner. This build keeps account identity fixed so story ownership cannot drift.</p>
						</SettingsPanel>
					)}
					{section === 'ai' && (
						<SettingsPanel id="ai" eyebrow="MODEL & CONNECTION" title="AI & API" description="Choose the provider that reads your manuscript when you ask for a check. Keys stay encrypted and are never shown again.">
							<AIProviderSettingsForm showHeading={false} />
						</SettingsPanel>
					)}
					{section === 'security' && (
						<SettingsPanel id="security" eyebrow="SECURITY" title="Password" description="Changing it signs out every device, including this one. You will sign in again with the new password.">
							<form className="account-form settings-form" onSubmit={changePassword}>
								<label>Current password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required autoComplete="current-password" /></label>
								<label>New password<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required minLength={10} autoComplete="new-password" /></label>
								<label>Confirm new password<input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength={10} autoComplete="new-password" /></label>
								{accountNotice && <p className="form-notice" role="status">{accountNotice}</p>}
								{accountError && <p className="form-error" role="alert">{accountError}</p>}
								<button className="button button-primary" disabled={busy}>{busy ? 'Changing…' : 'Change password'}</button>
							</form>
						</SettingsPanel>
					)}
					{section === 'sessions' && (
						<SettingsPanel id="sessions" eyebrow="SESSIONS" title="Where you are signed in" description="Each row is one browser session. Revoke anything you do not recognise.">
							{accountNotice && <p className="form-notice" role="status">{accountNotice}</p>}
							{accountError && <p className="form-error" role="alert">{accountError}</p>}
							<ul className="settings-session-list">
								{sessions.map((session) => <li key={session.id}>
									<div><strong>{deviceName(session.user_agent)} {session.current && <span className="settings-chip">This device</span>}</strong><span>{session.ip || 'Unknown address'} · signed in {shortDate(session.created_at)} · last seen {shortDate(session.last_seen_at)}</span></div>
									<button className="quiet-button" onClick={() => void revoke(session)}>{session.current ? 'Sign out' : 'Revoke'}</button>
								</li>)}
							</ul>
							{sessions.length === 0 && <p className="settings-note">No active sessions were returned.</p>}
							<div className="settings-actions"><button className="quiet-button" onClick={() => void revokeEverywhere()}>Sign out everywhere</button></div>
						</SettingsPanel>
					)}
					{section === 'data' && (
						<>
							<SettingsPanel id="data" eyebrow="YOUR DATA" title="Take it with you" description="Download every story, chapter, wiki entry, draft file, and preference in one archive. Provider API keys are never included.">
								<div className="settings-actions"><a className="button button-primary" href={api.accountExportUrl} download>Export all my data (.zip)</a></div>
								<p className="settings-note">Deleted stories and chapters wait in the trash for 30 days. Deleting your account removes everything immediately, including that trash; the export above is the only copy you keep.</p>
							</SettingsPanel>
							<SettingsPanel id="delete-account" eyebrow="DANGER ZONE" title="Delete this account" description="This removes your account and every story, chapter, wiki entry, upload, session, and setting. It cannot be undone and is not limited to the trash." danger>
								<form className="account-form settings-form" onSubmit={deleteAccount}>
									<label>Type your username to confirm<input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} required autoComplete="off" placeholder={user?.username ?? 'username'} /></label>
									<label>Password<input type="password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} required autoComplete="current-password" /></label>
									{deleteError && <p className="form-error" role="alert">{deleteError}</p>}
									<button className="button danger-button" disabled={deleting}>{deleting ? 'Deleting…' : 'Delete my account and data'}</button>
								</form>
							</SettingsPanel>
						</>
					)}
					{section === 'activity' && (
						<SettingsPanel id="activity" eyebrow="ACTIVITY" title="Recent account changes" description="The last few sensitive actions on this account. Each entry keeps only a short description, an address, and a time; story prose is never written to this log.">
							<ul className="settings-audit-list">
								{audit.map((event) => <li key={event.id}>
									<div><strong>{ACTION_LABELS[event.action] ?? event.action.replaceAll('_', ' ')}</strong>
										{typeof event.detail.title === 'string' && <span>{event.detail.title}</span>}
										<span>{shortDate(event.created_at)} · {event.ip || 'unknown address'}</span></div>
								</li>)}
							</ul>
							{audit.length === 0 && <p className="settings-note">No activity has been recorded yet.</p>}
						</SettingsPanel>
					)}
					<footer className="settings-foot"><span>Stillroom keeps the details. The story stays yours.</span><Link href={backHref}>{backLabel} →</Link></footer>
				</div>
			</div>
		</main>
	</AppShell>;
}
