'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { api } from '@/lib/api';

export default function LoginPage() {
	const router = useRouter();
	const [mode, setMode] = useState<'signin' | 'signup'>('signin');
	const [username, setUsername] = useState('');
	const [email, setEmail] = useState('');
	const [password, setPassword] = useState('');
	const [error, setError] = useState('');
	const [busy, setBusy] = useState(false);

	async function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setBusy(true);
		setError('');
		try {
			if (mode === 'signup') await api.register(username, email, password);
			await api.login(email, password);
			router.replace('/dashboard');
		} catch (cause) {
			setError(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'Please try again.');
		} finally {
			setBusy(false);
		}
	}

	return (
		<main className="auth-screen">
			<Link className="wordmark" href="/"><span className="wordmark-icon">s</span>stillroom</Link>
			<section className="auth-card">
				<div className="eyebrow">A QUIETER KIND OF WRITING TOOL</div>
				<h1>{mode === 'signin' ? 'Welcome back.' : 'Make room for your story.'}</h1>
				<p className="auth-intro">Your words stay yours. Stillroom keeps the details in order.</p>
				<form className="auth-form" onSubmit={submit}>
					{mode === 'signup' && <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} required minLength={2} maxLength={40} autoComplete="username" /></label>}
					<label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" /></label>
					<label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={mode === 'signup' ? 10 : undefined} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} /></label>
					{error && <p className="form-error" role="alert">{error}</p>}
					<button className="button button-primary button-wide" disabled={busy}>{busy ? 'One moment…' : mode === 'signin' ? 'Sign in' : 'Create account'}</button>
				</form>
				<p className="auth-switch">{mode === 'signin' ? 'New to Stillroom?' : 'Already have an account?'}{' '}
					<button className="text-button" onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setError(''); }}>
						{mode === 'signin' ? 'Create an account' : 'Sign in'}
					</button>
				</p>
			</section>
			<p className="auth-footnote">No generated prose. Just space to write, and help keeping your story straight.</p>
		</main>
	);
}
