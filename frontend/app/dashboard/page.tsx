'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { Toaster, toast } from 'sonner';
import { AppShell } from '@/components/app-shell';
import { ConfirmProvider, useConfirm } from '@/components/confirm-dialog';
import { StoryNameDialog } from '@/components/story-name-dialog';
import { api, type CurrentUser, type Story, type TrashListing } from '@/lib/api';
import { isUnauthorized } from '@/lib/auth-redirect';

export default function DashboardPage() {
	return (
		<ConfirmProvider>
			<Toaster position="bottom-right" richColors closeButton />
			<DashboardInner />
		</ConfirmProvider>
	);
}

function DashboardInner() {
	const confirm = useConfirm();
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
	const [rename, setRename] = useState<{ story: Story; field: 'title' | 'collection_name' } | null>(null);
	const [trash, setTrash] = useState<TrashListing | null>(null);
	const [trashBusy, setTrashBusy] = useState(false);

	useEffect(() => {
		let active = true;
		Promise.all([api.me(), api.stories()]).then(([account, items]) => {
			if (active) { setUser(account); setStories(items); }
		}).catch((cause: unknown) => {
			if (!active) return;
			if (isUnauthorized(cause)) return;
			setError(cause instanceof Error ? cause.message : 'Your stories could not be loaded.');
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

	async function deleteStory(story: Story) {
		const ok = await confirm({
			title: 'Move this story to the trash?',
			description: `“${story.title}” and its chapters can be restored from the trash for 30 days.`,
			confirmLabel: 'Move to trash',
			destructive: true,
		});
		if (!ok) return;
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

	async function submitStoryName(value: string) {
		if (!rename) return;
		const { story, field } = rename;
		if (value === story[field]) { setRename(null); return; }
		try {
			const updated = await api.updateStory(story.id, { [field]: value });
			setStories((current) => current.map((item) => item.id === story.id ? { ...item, ...updated } : item));
			toast.success(field === 'title' ? 'Story renamed.' : 'Collection updated.');
			setRename(null);
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'The story could not be updated.');
		}
	}

	async function openTrash() {
		setTrashBusy(true);
		try {
			setTrash(await api.trash());
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'The trash could not be loaded.');
		} finally {
			setTrashBusy(false);
		}
	}

	async function restoreChapter(item: { id: string; title: string }) {
		try {
			const result = await api.restoreTrashChapter(item.id);
			toast.success(result.renumbered_from
				? `Restored as chapter ${result.chapter.chapter_number} because its old number was taken.`
				: 'Chapter restored.');
			setStories(await api.stories());
			await openTrash();
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'The chapter could not be restored.');
		}
	}

	async function restoreStory(item: { id: string; title: string }) {
		try {
			await api.restoreTrashStory(item.id);
			toast.success('Story restored.');
			setStories(await api.stories());
			await openTrash();
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'The story could not be restored.');
		}
	}

	async function purgeChapter(item: { id: string; title: string }) {
		const ok = await confirm({
			title: 'Delete this chapter forever?',
			description: `“${item.title}” will not be recoverable.`,
			confirmLabel: 'Delete forever',
			destructive: true,
		});
		if (!ok) return;
		try {
			await api.deleteTrashChapter(item.id);
			toast.success('Chapter deleted permanently.');
			await openTrash();
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'The chapter could not be deleted.');
		}
	}

	async function purgeStory(item: { id: string; title: string }) {
		const ok = await confirm({
			title: 'Delete this story forever?',
			description: `“${item.title}” and every chapter in it will not be recoverable.`,
			confirmLabel: 'Delete forever',
			destructive: true,
		});
		if (!ok) return;
		try {
			await api.deleteTrashStory(item.id);
			toast.success('Story deleted permanently.');
			await openTrash();
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'The story could not be deleted.');
		}
	}

	if (loading) return <main className="quiet-loading"><span className="loading-mark" /><p>Opening your desk…</p></main>;
	const collections = [...new Set(stories.map((story) => story.collection_name).filter(Boolean))].sort((a, b) => a.localeCompare(b));
	const visibleStories = stories.filter((story) =>
		story.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
		(collectionFilter === 'all' || story.collection_name === collectionFilter),
	);
	const totalWords = stories.reduce((sum, story) => sum + (story.word_count ?? 0), 0);
	const totalChapters = stories.reduce((sum, story) => sum + (story.chapter_count ?? 0), 0);
	const recent = [...stories].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0];
	const coverFor = (story: Story) => {
		let hash = 0;
		for (const character of story.title) hash = (hash * 31 + character.charCodeAt(0)) % 360;
		const palettes = [
			['#1e293b', '#64748b'], ['#7c2d12', '#c2704a'], ['#1e3a5f', '#3b82f6'],
			['#78350f', '#b45309'], ['#3b0764', '#7e22ce'], ['#4c1d2f', '#a34d6b'],
		];
		const pair = palettes[hash % palettes.length];
		return { background: `linear-gradient(145deg, ${pair[0]}, ${pair[1]})` };
	};

	return (
		<AppShell active="library" user={user?.username}>
			<section className="library-content library-home">
				<div className="library-hero">
					<div className="library-hero-copy">
						<div className="eyebrow"><span className="eyebrow-rule" /> STILLROOM / YOUR LIBRARY</div>
						<h1>Pick up a thread.<br /><em>Leave a mark.</em></h1>
						<p>Every story keeps its own rooms: the pages, the people, the promises still waiting to be paid.</p>
						<form className="hero-create" onSubmit={createStory}>
							<label htmlFor="new-story-title">Start something new</label>
							<div><input id="new-story-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Give the story a working title" maxLength={200} aria-label="Story title" required /><button className="button button-primary" disabled={busy}>{busy ? 'Opening…' : 'Open a desk →'}</button></div>
						</form>
					</div>
					<aside className="library-hero-aside" aria-label="Your library at a glance">
						<div className="desk-stats">
							<div><strong>{stories.length}</strong><span>{stories.length === 1 ? 'story' : 'stories'}</span></div>
							<div><strong>{totalChapters}</strong><span>chapters</span></div>
							<div><strong>{totalWords >= 1000 ? `${(totalWords / 1000).toFixed(totalWords >= 10000 ? 0 : 1)}k` : totalWords}</strong><span>words kept</span></div>
						</div>
						{recent ? (
							<Link className="continue-card" href={`/stories/${recent.id}`}>
								<div className="continue-cover" style={coverFor(recent)}><span>{recent.title.slice(0, 1)}</span></div>
								<div><span className="continue-kicker">CONTINUE WRITING</span><strong>{recent.title}</strong><small>{recent.chapter_count ?? 0} chapters · last touched {new Date(recent.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</small></div>
								<span className="continue-arrow" aria-hidden="true">→</span>
							</Link>
						) : (
							<div className="continue-card continue-card-empty"><span className="continue-kicker">A FRESH PAGE</span><p>Your first story will appear here.</p></div>
						)}
					</aside>
				</div>
				{error && <div className="notice" role="alert">{error}</div>}
				<div className="library-heading"><div><div className="eyebrow">THE SHELF</div><h2>Your stories</h2></div><span>{visibleStories.length} of {stories.length}</span></div>
				{stories.length > 0 && <div className="story-library-tools"><label className="shelf-search"><span aria-hidden="true">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search the shelf" aria-label="Search stories" /></label><select value={collectionFilter} onChange={(event) => setCollectionFilter(event.target.value)} aria-label="Filter by collection"><option value="all">All collections</option>{collections.map((collection) => <option key={collection} value={collection}>{collection}</option>)}</select><span className="shelf-hint">Drag nothing. Just write.</span></div>}
				{visibleStories.length ? <div className="story-grid">{visibleStories.map((story, index) => <article className="story-card" key={story.id}>
					<Link className="story-card-link" href={`/stories/${story.id}`}>
						<div className="story-cover" style={coverFor(story)}>
							<span className="story-cover-kicker">STILLROOM · {String(index + 1).padStart(2, '0')}</span>
							<span className="story-cover-glyph" aria-hidden="true">{story.title.slice(0, 2)}</span>
							<span className="story-cover-rule" aria-hidden="true" />
							<span className="story-cover-collection">{story.collection_name || 'Unfiled'}</span>
						</div>
						<div className="story-card-copy">
							<div className="story-card-topline"><span>{story.chapter_count ?? 0} {(story.chapter_count ?? 0) === 1 ? 'chapter' : 'chapters'}</span><span>{(story.word_count ?? 0).toLocaleString()} words</span></div>
							<h3>{story.title}</h3>
							<p className="story-blurb">{(story.word_count ?? 0) > 0 ? 'The next sentence is already waiting.' : 'A blank page with room to begin.'}</p>
							{(story.chapter_count ?? 0) >= (story.chapter_warning_at ?? 1000) && <p className="story-size-warning">This story is very long. Consider splitting the manuscript into volumes; Stillroom will keep working, but navigation gets heavy.</p>}
							<div className="story-card-foot"><span>Last tended</span><time>{new Date(story.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time><span className="story-open">Open</span></div>
						</div>
					</Link>
					<div className="story-card-actions"><button className="story-delete-button" onClick={() => setRename({ story, field: 'title' })}>Rename</button><button className="story-delete-button" onClick={() => setRename({ story, field: 'collection_name' })}>Collection</button><button className="story-delete-button" onClick={() => void deleteStory(story)} disabled={deletingStoryId === story.id}>{deletingStoryId === story.id ? 'Deleting…' : 'Delete'}</button></div>
				</article>)}</div> : <div className="library-empty"><span className="empty-glyph">✳</span><h3>{stories.length ? 'Nothing on this part of the shelf.' : 'Your first page is waiting.'}</h3><p>{stories.length ? 'Try another search or collection.' : 'Create a story above to open your writing desk.'}</p>{!stories.length && <div className="empty-steps"><span><b>1</b> Name it</span><span><b>2</b> Write a chapter</span><span><b>3</b> Let the wiki remember</span></div>}</div>}
				<section className="trash-panel" aria-label="Trash">
					<header>
						<h2>Trash</h2>
						<button className="quiet-button" onClick={() => void openTrash()} disabled={trashBusy}>{trashBusy ? 'Loading…' : trash ? 'Refresh' : 'Open trash'}</button>
					</header>
					{trash && <>
						<p className="retention">Deleted stories and chapters stay here for {trash.retention_days} days, then they are removed permanently.</p>
						{trash.stories.length === 0 && trash.chapters.length === 0 && <p className="trash-empty">The trash is empty.</p>}
						{trash.stories.map((item) => (
							<div className="trash-row" key={item.id}>
								<div><strong>{item.title}</strong><span>{item.chapter_count} {item.chapter_count === 1 ? 'chapter' : 'chapters'} · whole story</span><time>Deleted {item.deleted_at ? new Date(item.deleted_at).toLocaleDateString() : 'recently'}</time></div>
								<div className="trash-actions"><button className="text-button" onClick={() => void restoreStory(item)}>Restore</button><button className="text-button subtle" onClick={() => void purgeStory(item)}>Delete forever</button></div>
							</div>
						))}
						{trash.chapters.map((item) => (
							<div className="trash-row" key={item.id}>
								<div><strong>{item.title}</strong><span>{item.story_title} · chapter {item.chapter_number} · {item.word_count.toLocaleString()} words</span><time>Deleted {item.deleted_at ? new Date(item.deleted_at).toLocaleDateString() : 'recently'}</time></div>
								<div className="trash-actions"><button className="text-button" onClick={() => void restoreChapter(item)}>Restore</button><button className="text-button subtle" onClick={() => void purgeChapter(item)}>Delete forever</button></div>
							</div>
						))}
					</>}
				</section>
				<footer className="library-footer">Stillroom keeps the details. The story stays yours.</footer>
			</section>
			<StoryNameDialog
				open={rename !== null}
				title={rename?.field === 'title' ? 'Rename story' : 'Change collection'}
				label={rename?.field === 'title' ? 'Story title' : 'Collection name'}
				description={rename?.field === 'collection_name' ? 'Leave blank to move it out of any collection.' : undefined}
				initialValue={rename ? (rename.field === 'title' ? rename.story.title : rename.story.collection_name) : ''}
				placeholder={rename?.field === 'title' ? 'A working title' : 'No collection'}
				allowEmpty={rename?.field === 'collection_name'}
				onSubmit={submitStoryName}
				onCancel={() => setRename(null)}
			/>
		</AppShell>
	);
}
