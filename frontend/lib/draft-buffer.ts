import { openDB, type DBSchema, type IDBPDatabase } from 'idb';

export type DraftRecord = {
	chapterId: string;
	storyId: string;
	title: string;
	content: string;
	revision: number;
	updatedAt: number;
	dirty: boolean;
};

interface DraftSchema extends DBSchema {
	drafts: {
		key: string;
		value: DraftRecord;
		indexes: { 'by-story': string };
	};
}

const DB_NAME = 'stillroom-drafts';
const DB_VERSION = 1;
const STORE = 'drafts';

let dbPromise: Promise<IDBPDatabase<DraftSchema>> | null = null;

export function openDraftDb(): Promise<IDBPDatabase<DraftSchema>> {
	if (typeof indexedDB === 'undefined') {
		return Promise.reject(new Error('IndexedDB is not available in this environment.'));
	}
	dbPromise ??= openDB<DraftSchema>(DB_NAME, DB_VERSION, {
		upgrade(db) {
			const store = db.createObjectStore(STORE, { keyPath: 'chapterId' });
			store.createIndex('by-story', 'storyId');
		},
	});
	return dbPromise;
}

export async function putDraft(record: DraftRecord): Promise<void> {
	const db = await openDraftDb();
	await db.put(STORE, record);
}

export async function getDraft(chapterId: string): Promise<DraftRecord | undefined> {
	const db = await openDraftDb();
	return db.get(STORE, chapterId);
}

export async function deleteDraft(chapterId: string): Promise<void> {
	const db = await openDraftDb();
	await db.delete(STORE, chapterId);
}

export async function listDirtyDrafts(storyId?: string): Promise<DraftRecord[]> {
	const db = await openDraftDb();
	const records = storyId
		? await db.getAllFromIndex(STORE, 'by-story', storyId)
		: await db.getAll(STORE);
	return records.filter((record) => record.dirty);
}

export type DraftDecision =
	| { action: 'server' }
	| { action: 'use-local'; reason: 'recovered' }
	| { action: 'conflict'; localContent: string };

/**
 * Decide what to show when a chapter opens.
 *
 * Revision ordering is the only reliable one — wall clocks disagree between
 * tabs and machines. A dirty buffer at the same revision is the writer's own
 * unsaved work; anything else is a conflict or a stale copy.
 */
export function decideDraft(
	server: { revision: number; title: string; content: string },
	buffer: DraftRecord | undefined,
): DraftDecision {
	if (!buffer || (!buffer.dirty && buffer.content === server.content && buffer.title === server.title)) {
		return { action: 'server' };
	}
	if (buffer.revision === server.revision) {
		if (buffer.content === server.content && buffer.title === server.title) {
			return { action: 'server' };
		}
		return { action: 'use-local', reason: 'recovered' };
	}
	return { action: 'conflict', localContent: buffer.content };
}

/** Clear the buffer only when the server stored exactly what is on screen. */
export async function clearBufferIfSaved(
	chapterId: string,
	saved: { title: string; content: string },
): Promise<boolean> {
	const buffer = await getDraft(chapterId);
	if (!buffer) return true;
	if (buffer.title === saved.title && buffer.content === saved.content) {
		await deleteDraft(chapterId);
		return true;
	}
	return false;
}
