export type EditorTheme = 'paper' | 'sepia' | 'night';

export interface EditorPreferences {
	fontSize: number;
	lineHeight: number;
	measure: number;
	fontFamily: 'serif' | 'sans';
	theme: EditorTheme;
	typewriter: boolean;
	focusMode: boolean;
	wordGoal: number;
}

export const DEFAULT_EDITOR_PREFERENCES: EditorPreferences = {
	fontSize: 19,
	lineHeight: 1.75,
	measure: 720,
	fontFamily: 'serif',
	theme: 'paper',
	typewriter: false,
	focusMode: false,
	wordGoal: 0,
};

const STORAGE_KEY = 'stillroom:editor-preferences';

let cachedPreferences: EditorPreferences | null = null;
const listeners = new Set<() => void>();

export function loadEditorPreferences(): EditorPreferences {
	if (typeof window === 'undefined') return DEFAULT_EDITOR_PREFERENCES;
	try {
		const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<EditorPreferences>;
		return {
			...DEFAULT_EDITOR_PREFERENCES,
			...parsed,
			fontSize: clamp(parsed.fontSize ?? DEFAULT_EDITOR_PREFERENCES.fontSize, 14, 32),
			lineHeight: clamp(parsed.lineHeight ?? DEFAULT_EDITOR_PREFERENCES.lineHeight, 1.3, 2.4),
			measure: clamp(parsed.measure ?? DEFAULT_EDITOR_PREFERENCES.measure, 480, 1200),
			wordGoal: Math.max(0, Math.floor(parsed.wordGoal ?? 0)),
		};
	} catch {
		return DEFAULT_EDITOR_PREFERENCES;
	}
}

export function saveEditorPreferences(preferences: EditorPreferences): void {
	if (typeof window === 'undefined') return;
	window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
}

/** Snapshot for useSyncExternalStore; the object identity is stable until changed. */
export function getEditorPreferencesSnapshot(): EditorPreferences {
	cachedPreferences ??= loadEditorPreferences();
	return cachedPreferences;
}

export function getServerEditorPreferencesSnapshot(): EditorPreferences {
	return DEFAULT_EDITOR_PREFERENCES;
}

export function subscribeEditorPreferences(listener: () => void): () => void {
	listeners.add(listener);
	return () => listeners.delete(listener);
}

export function updateEditorPreferences(next: EditorPreferences): void {
	cachedPreferences = next;
	saveEditorPreferences(next);
	for (const listener of listeners) listener();
}

function clamp(value: number, minimum: number, maximum: number): number {
	return Math.min(Math.max(value, minimum), maximum);
}