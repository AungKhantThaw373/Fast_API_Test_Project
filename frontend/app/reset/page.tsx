'use client';

import Link from 'next/link';
import { useEffect, useState, type FormEvent } from 'react';
import { api, ensureCsrf } from '@/lib/api';

export default function ResetPasswordPage() {
	const [token, setToken] = useState('');
	const [password, setPassword] = useState('');
	const [confirm, setConfirm] = useState('');
	const [error, setError] = useState('');
	const [done, setDone] = useState(false);
	const [busy, setBusy] = useState(false);

	useEffect(() => {
		void ensureCsrf();
		// The token arrives in the URL the browser opened.
		// eslint-disable-next-line react-hooks/set-state-in-effect
		setToken(new URLSearchParams(window.location.search).get('token') ?? '');
	}, []);

	async function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError('');
		if (password !== confirm) {
			setError('The two passwords do not match.');
			return;
		}
		setBusy(true);
		try {
			await ensureCsrf();
			await api.resetPassword(token, password);
			setDone(true);
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
				<div className="eyebrow">ACCOUNT RECOVERY</div>
				<h1>{done ? 'Back in your hands.' : 'Choose a new password.'}</h1>
				{done ? (
					<>
						<p className="auth-intro">Every device has been signed out. Use the new password to sign in again.</p>
						<p className="auth-switch"><Link className="button button-primary button-wide" href="/login?reset=done">Go to sign in</Link></p>
					</>
				) : (
					<form className="auth-form" onSubmit={submit}>
						{!token && <p className="form-error" role="alert">This reset link is missing its token. Request a new link.</p>}
						<label>New password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={10} autoComplete="new-password" /></label>
						<label>Confirm new password<input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required minLength={10} autoComplete="new-password" /></label>
						{error && <p className="form-error" role="alert">{error}</p>}
						<button className="button button-primary button-wide" disabled={busy || !token}>{busy ? 'Changing…' : 'Change password'}</button>
					</form>
				)}
				{!done && <p className="auth-switch"><Link className="text-button" href="/forgot">Request a new link</Link></p>}
			</section>
		</main>
	);
}