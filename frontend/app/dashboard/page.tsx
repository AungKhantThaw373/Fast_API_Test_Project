'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { api, type CurrentUser, type Story } from '@/lib/api';

export default function DashboardPage() {
	const router = useRouter();
	const [user, setUser] = useState<CurrentUser | null>(null);
	const [stories, setStories] = useState<Story[]>([]);
	const [title, setTitle] = useState('');
	const [loading, setLoading] = useState(true);
	const [busy, setBusy] = useState(false);
	const [deletingStoryId, setDeletingStoryId] = useState<string | null>(null);
	const [search, setSearch] = useState('');
	const [collectionFilter, setCollectionFilter] = useState('all');
	const [error, setError] = useState('');

	useEffect(() => {
		let active = true;
		Promise.all([api.me(), api.stories()]).then(([account, items]) => {
			if (active) { setUser(account); setStories(items); }
		}).catch((cause: unknown) => {
			if (!active) return;
			if (cause instanceof Error && cause.message.includes('(401)')) router.replace('/login');
			else setError(cause instanceof Error ? cause.message : 'Your stories could not be loaded.');
		}).finally(() => { if (active) setLoading(false); });
		return () => { active = false; };
	}, [router]);

	async function createStory(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (!title.trim()) return;
		setBusy(true); setError('');
		try {
			const story = await api.createStory(title.trim());
			router.push(`/stories/${story.id}`);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'The story could not be created.');
			setBusy(false);
		}
	}

	async function logout() {
		try { await api.logout(); } finally { router.replace('/login'); }
	}

	async function deleteStory(story: Story) {
		if (!window.confirm(`Delete “${story.title}” and all of its chapters? This cannot be undone.`)) return;
		setDeletingStoryId(story.id);
		setError('');
		try {
			await api.deleteStory(story.id);
			setStories((current) => current.filter((item) => item.id !== story.id));
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'The story could not be deleted.');
		} finally {
			setDeletingStoryId(null);
		}
	}

	async function editStory(story: Story, field: 'title' | 'collection_name') {
		const promptText = field === 'title' ? 'Rename story' : 'Move to collection (leave blank for no collection)';
		const value = window.prompt(promptText, field === 'title' ? story.title : story.collection_name)?.trim();
		if (value === undefined || (field === 'title' && !value) || value === story[field]) return;
		try {
			const updated = await api.updateStory(story.id, { [field]: value });
			setStories((current) => current.map((item) => item.id === story.id ? { ...item, ...updated } : item));
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'The story could not be updated.'); }
	}

	if (loading) return <main className="quiet-loading"><span className="loading-mark" /><p>Opening your desk…</p></main>;
	const collections = [...new Set(stories.map((story) => story.collection_name).filter(Boolean))].sort((a, b) => a.localeCompare(b));
	const visibleStories = stories.filter((story) =>
		story.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
		(collectionFilter === 'all' || story.collection_name === collectionFilter),
	);

	return (
		<main className="library-page">
			<header className="library-header">
				<div className="app-header-left">
					<Link className="wordmark" href="/dashboard"><span className="wordmark-icon">s</span>stillroom</Link>
					<nav className="product-nav" aria-label="Workspace">
						<Link href="/dashboard" aria-current="page">Writing</Link>
						<Link href="/editing">Editing</Link>
						<Link href="/settings">Settings</Link>
					</nav>
				</div>
				<div className="header-account"><Link className="profile-link" href="/settings">{user?.username}</Link><button className="quiet-button" onClick={() => void logout()}>Sign out</button></div>
			</header>
			<section className="library-content">
				<div className="welcome-block"><div className="eyebrow">YOUR WRITING DESK</div><h1>Make room for a story.</h1><p>A quiet place for the pages, and a careful eye on the details.</p></div>
				{error && <div className="notice" role="alert">{error}</div>}
				<form className="new-story-card" onSubmit={createStory}>
					<div className="new-story-mark">+</div>
					<div className="new-story-copy"><strong>Begin a new story</strong><span>Start with a title. You can change it whenever you like.</span></div>
					<div className="new-story-controls"><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="A working title" maxLength={200} aria-label="Story title" required /><button className="button button-primary" disabled={busy}>{busy ? 'Opening…' : 'Open writing desk'}</button></div>
				</form>
				<div className="library-heading"><div><div className="eyebrow">YOUR WORK</div><h2>Stories</h2></div><span>{visibleStories.length} of {stories.length}</span></div>
				{stories.length > 0 && <div className="story-library-tools"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a story" aria-label="Search stories" /><select value={collectionFilter} onChange={(event) => setCollectionFilter(event.target.value)} aria-label="Filter by collection"><option value="all">All collections</option>{collections.map((collection) => <option key={collection} value={collection}>{collection}</option>)}</select></div>}
				{visibleStories.length ? <div className="story-grid">{visibleStories.map((story) => <article className="story-card" key={story.id}>
					<Link className="story-card-link" href={`/stories/${story.id}`}>
						<div className="story-card-top"><span className="story-card-mark">✳</span><span className="story-open">{story.collection_name || 'Unsorted'} · Open ↗</span></div>
						<h3>{story.title}</h3><p>{story.chapter_count ?? 0} {(story.chapter_count ?? 0) === 1 ? 'chapter' : 'chapters'} <span>·</span> {(story.word_count ?? 0).toLocaleString()} words</p>
						<div className="story-card-foot"><span>Last tended</span><time>{new Date(story.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time></div>
					</Link>
					<div className="story-card-actions"><button className="story-delete-button" onClick={() => void editStory(story, 'title')}>Rename</button><button className="story-delete-button" onClick={() => void editStory(story, 'collection_name')}>Collection</button><button className="story-delete-button" onClick={() => void deleteStory(story)} disabled={deletingStoryId === story.id}>{deletingStoryId === story.id ? 'Deleting…' : 'Delete'}</button></div>
				</article>)}</div> : <div className="library-empty"><span>✳</span><h3>{stories.length ? 'No stories match that filter.' : 'Your first page is waiting.'}</h3><p>{stories.length ? 'Try another search or collection.' : 'Create a story above to open your writing desk.'}</p></div>}
				<footer className="library-footer">Stillroom keeps the details. The story stays yours.</footer>
			</section>
		</main>
	);
}
