import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it } from 'vitest';
import {
	clearBufferIfSaved,
	decideDraft,
	deleteDraft,
	getDraft,
	listDirtyDrafts,
	putDraft,
	type DraftRecord,
} from '../draft-buffer';

const base: DraftRecord = {
	chapterId: 'chapter-1',
	storyId: 'story-1',
	title: 'Chapter one',
	content: 'The first draft.',
	revision: 3,
	updatedAt: Date.now(),
	dirty: true,
};

beforeEach(async () => {
	await deleteDraft('chapter-1');
	await deleteDraft('chapter-2');
});

describe('draft buffer', () => {
	it('round-trips a draft record', async () => {
		await putDraft(base);
		expect(await getDraft('chapter-1')).toMatchObject({ content: 'The first draft.', revision: 3 });
	});

	it('lists only dirty drafts for a story', async () => {
		await putDraft(base);
		await putDraft({ ...base, chapterId: 'chapter-2', dirty: false, content: 'Saved already.' });
		const dirty = await listDirtyDrafts('story-1');
		expect(dirty.map((record) => record.chapterId)).toEqual(['chapter-1']);
	});
});

describe('clearBufferIfSaved', () => {
	it('clears the buffer when the saved text matches exactly', async () => {
		await putDraft(base);
		const cleared = await clearBufferIfSaved('chapter-1', { title: base.title, content: base.content });
		expect(cleared).toBe(true);
		expect(await getDraft('chapter-1')).toBeUndefined();
	});

	it('keeps the buffer when the writer typed during the save', async () => {
		await putDraft(base);
		const cleared = await clearBufferIfSaved('chapter-1', { title: base.title, content: 'Something older.' });
		expect(cleared).toBe(false);
		expect(await getDraft('chapter-1')).toBeTruthy();
	});

	it('keeps the buffer when the title changed during the save', async () => {
		await putDraft(base);
		const cleared = await clearBufferIfSaved('chapter-1', { title: 'Renamed', content: base.content });
		expect(cleared).toBe(false);
	});
});

describe('decideDraft', () => {
	const server = { revision: 5, title: 'Chapter one', content: 'Server text.' };

	it('uses the server when there is no buffer', () => {
		expect(decideDraft(server, undefined)).toEqual({ action: 'server' });
	});

	it('uses the server when the buffer already matches it', () => {
		expect(decideDraft(server, { ...base, revision: 5, content: 'Server text.', dirty: false }))
			.toEqual({ action: 'server' });
	});

	it('recovers a dirty buffer at the same revision', () => {
		expect(decideDraft(server, { ...base, revision: 5, content: 'Unsaved words.' }))
			.toEqual({ action: 'use-local', reason: 'recovered' });
	});

	it('treats a revision mismatch as a conflict, never a silent discard', () => {
		const decision = decideDraft(server, { ...base, revision: 4, content: 'Local words.' });
		expect(decision).toEqual({ action: 'conflict', localContent: 'Local words.' });
	});

	it('compares revisions, not timestamps', () => {
		const now = Date.now();
		// A buffer that claims to be newer by clock but older by revision.
		const decision = decideDraft(server, {
			...base,
			revision: 4,
			updatedAt: now + 60_000,
			content: 'Local words.',
		});
		expect(decision.action).toBe('conflict');
	});
});
