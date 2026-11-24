'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, type CurrentUser } from '@/lib/api';

export default function GeneralSettingsPage() {
	const router = useRouter();
	const [user, setUser] = useState<CurrentUser | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		let active = true;
		api.me().then((account) => { if (active) setUser(account); }).catch((cause: unknown) => {
			if (!active) return;
			if (cause instanceof Error && cause.message.includes('(401)')) router.replace('/login');
		}).finally(() => { if (active) setLoading(false); });
		return () => { active = false; };
	}, [router]);

	async function logout() {
		try { await api.logout(); } finally { router.replace('/login'); }
	}

	if (loading) return <main className="quiet-loading"><span className="loading-mark" /><p>Opening settings…</p></main>;

	return <main className="library-page">
		<header className="library-header">
			<div className="app-header-left">
				<Link className="wordmark" href="/dashboard"><span className="wordmark-icon">s</span>stillroom</Link>
				<nav className="product-nav" aria-label="Workspace"><Link href="/dashboard">Writing</Link><Link href="/editing">Editing</Link><Link href="/settings" aria-current="page">Settings</Link></nav>
			</div>
			<div className="header-account"><span>{user?.username}</span><button className="quiet-button" onClick={() => void logout()}>Sign out</button></div>
		</header>
		<section className="general-settings-page">
			<div className="eyebrow">ACCOUNT PREFERENCES</div>
			<h1>Settings</h1>
			<p className="general-settings-intro">Your account and website preferences.</p>
			<div className="general-settings-layout">
				<nav className="general-settings-nav" aria-label="Settings sections"><span className="selected">Profile</span><a href="#privacy">Privacy</a></nav>
				<div className="general-settings-main"><section className="profile-settings-card"><div className="eyebrow">PROFILE</div><h2>Account details</h2><dl><div><dt>Username</dt><dd>{user?.username ?? '—'}</dd></div><div><dt>Email</dt><dd>{user?.email ?? '—'}</dd></div></dl></section><section className="general-privacy" id="privacy"><div className="eyebrow">PRIVACY</div><h2>Your story data</h2><p>AI provider settings and each story’s analysis controls live together in the AI Settings tab on the right side of the Writing desk. When enabled, chapter text and relevant earlier excerpts are sent to that provider. Local indexing stays on Ollama.</p><Link className="settings-writing-link" href="/dashboard">Go to Writing</Link></section></div>
			</div>
		</section>
	</main>;
}
