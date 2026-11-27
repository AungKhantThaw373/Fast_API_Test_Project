'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { ThemeToggle } from '@/components/theme-toggle';

type AppSection = 'library' | 'files' | 'settings' | 'diagnostics';

const NAV: { id: AppSection; href: string; label: string; number: string }[] = [
	{ id: 'library', href: '/dashboard', label: 'Library', number: '01' },
	{ id: 'files', href: '/editing', label: 'Files', number: '02' },
	{ id: 'settings', href: '/settings', label: 'Settings', number: '03' },
	{ id: 'diagnostics', href: '/diagnostics', label: 'Diagnostics', number: '04' },
];

export function AppShell({ active, user, children }: { active: AppSection; user?: string | null; children: React.ReactNode }) {
	const router = useRouter();
	const initial = (user?.trim()?.[0] ?? 's').toUpperCase();

	async function signOut() {
		try { await api.logout(); } finally { router.replace('/login'); }
	}

	return (
		<div className="app-frame">
			<aside className="app-rail" aria-label="Workspace">
				<Link className="app-rail-brand" href="/dashboard">
					<span className="app-rail-mark" aria-hidden="true">s</span>
					<span><strong>stillroom</strong><small>a place for the pages</small></span>
				</Link>
				<div className="app-rail-label">Workspace</div>
				<nav className="app-rail-nav">
					{NAV.map((item) => (
						<Link key={item.id} href={item.href} aria-current={active === item.id ? 'page' : undefined}>
							<span className="app-rail-number">{item.number}</span>
							<span>{item.label}</span>
						</Link>
					))}
				</nav>
				<div className="app-rail-foot">
					<div className="app-rail-user">
						<span className="app-avatar" aria-hidden="true">{initial}</span>
						<div><strong>{user || 'Your account'}</strong><Link href="/settings">Account settings</Link></div>
					</div>
					<div className="app-rail-tools"><ThemeToggle /><button className="app-rail-signout" onClick={() => void signOut()}>Sign out</button></div>
				</div>
			</aside>
			<div className="app-main">
				<header className="app-mobile-header">
					<Link className="app-mobile-brand" href="/dashboard"><span className="app-rail-mark">s</span>stillroom</Link>
					<div className="app-mobile-tools">
						<ThemeToggle compact />
						<Link className="app-mobile-account" href="/settings">{user || 'Account'}</Link>
					</div>
				</header>
				{children}
			</div>
			<nav className="app-bottom-nav" aria-label="Workspace">
				{NAV.map((item) => (
					<Link key={item.id} href={item.href} aria-current={active === item.id ? 'page' : undefined}>{item.label}</Link>
				))}
			</nav>
		</div>
	);
}