'use client';

import Link from 'next/link';
import { useEffect, useState, type FormEvent } from 'react';
import { api, ensureCsrf } from '@/lib/api';

export default function ForgotPasswordPage() {
	const [email, setEmail] = useState('');
	const [error, setError] = useState('');
	const [notice, setNotice] = useState('');
	const [busy, setBusy] = useState(false);

	useEffect(() => { void ensureCsrf(); }, []);

	async function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setBusy(true);
		setError('');
		try {
			await ensureCsrf();
			const response = await api.forgotPassword(email);
			setNotice(response.message);
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
				<h1>Find your way back.</h1>
				<p className="auth-intro">Enter the email on your account. On a local Stillroom install the reset link is printed in the server log; hosted installs send it by email.</p>
				<form className="auth-form" onSubmit={submit}>
					<label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" /></label>
					{notice && <p className="form-notice" role="status">{notice}</p>}
					{error && <p className="form-error" role="alert">{error}</p>}
					<button className="button button-primary button-wide" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button>
				</form>
				<p className="auth-switch"><Link className="text-button" href="/login">Back to sign in</Link></p>
			</section>
		</main>
	);
}