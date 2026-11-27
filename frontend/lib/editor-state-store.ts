import { openDB, type DBSchema, type IDBPDatabase } from 'idb';

export interface PersistedEditorState {
	chapterId: string;
	doc: string;
	json: unknown;
	updatedAt: number;
}

interface EditorStateSchema extends DBSchema {
	states: { key: string; value: PersistedEditorState };
}

const DB_NAME = 'stillroom-editor-state';
const DB_VERSION = 1;
const STORE = 'states';

let dbPromise: Promise<IDBPDatabase<EditorStateSchema>> | null = null;

function openStateDb(): Promise<IDBPDatabase<EditorStateSchema>> {
	if (typeof indexedDB === 'undefined') {
		return Promise.reject(new Error('IndexedDB is not available in this environment.'));
	}
	dbPromise ??= openDB<EditorStateSchema>(DB_NAME, DB_VERSION, {
		upgrade(db) {
			db.createObjectStore(STORE, { keyPath: 'chapterId' });
		},
	});
	return dbPromise;
}

export async function putEditorState(record: PersistedEditorState): Promise<void> {
	const db = await openStateDb();
	await db.put(STORE, record);
}

export async function getEditorState(chapterId: string): Promise<PersistedEditorState | undefined> {
	const db = await openStateDb();
	return db.get(STORE, chapterId);
}

export async function deleteEditorState(chapterId: string): Promise<void> {
	const db = await openStateDb();
	await db.delete(STORE, chapterId);
}