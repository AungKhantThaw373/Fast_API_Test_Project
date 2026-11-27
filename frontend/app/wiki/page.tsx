'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { AppShell } from '@/components/app-shell';
import { api, type Story } from '@/lib/api';

export default function WikiHubPage() {
	const router = useRouter();
	const [stories, setStories] = useState<Story[] | null>(null);
	const [error, setError] = useState('');

	useEffect(() => {
		let active = true;
		api.stories().then((rows) => {
			if (!active) return;
			setStories(rows);
			if (rows.length === 1) router.replace(`/stories/${rows[0].id}/wiki`);
		}).catch((cause: unknown) => {
			if (!active) return;
			setError(cause instanceof Error ? cause.message : 'The wiki could not be opened.');
			setStories([]);
		});
		return () => { active = false; };
	}, [router]);

	return <AppShell active="wiki">
		<main className="wiki-hub-page">
			<header className="wiki-hub-head">
				<div className="eyebrow">THE STORY BIBLE</div>
				<h1>Every entry,<br />in full.</h1>
				<p>People, places, facts, relationships, arcs, and open threads. Choose a novel to open its complete wiki — not the side dossier, the whole page.</p>
			</header>
			{error && <p className="form-error" role="alert">{error}</p>}
			{stories === null && !error && <div className="wiki-hub-loading"><span className="loading-mark" /><span>Opening the shelves…</span></div>}
			{stories?.length === 1 && <div className="wiki-hub-redirect">Opening the full wiki…</div>}
			{stories?.length === 0 && !error && (
				<div className="wiki-hub-empty">
					<div className="eyebrow">NOTHING HERE YET</div>
					<h2>Your wiki starts with a story.</h2>
					<p>Create a novel in the library. Its entries will gather here as you write and capture.</p>
					<Link className="button button-primary" href="/dashboard">Go to the library</Link>
				</div>
			)}
			{stories && stories.length > 1 && (
				<div className="wiki-hub-grid">
					{stories.map((story, index) => (
						<Link className="wiki-hub-card" href={`/stories/${story.id}/wiki`} key={story.id}>
							<div className="wiki-hub-card-top"><span>{String(index + 1).padStart(2, '0')}</span><span>{story.chapter_count ?? 0} {(story.chapter_count ?? 0) === 1 ? 'chapter' : 'chapters'}</span></div>
							<h2>{story.title}</h2>
							<p>{story.collection_name || 'Unfiled'} · {((story.word_count ?? 0) / 1000).toFixed((story.word_count ?? 0) >= 10000 ? 0 : 1)}k words</p>
							<span className="wiki-hub-open">Open the full wiki <span aria-hidden="true">→</span></span>
						</Link>
					))}
				</div>
			)}
		</main>
	</AppShell>;
}
