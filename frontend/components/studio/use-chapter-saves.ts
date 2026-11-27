	'use client';

	import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
	import { ApiRequestError, api, type BibleEntry, type Chapter } from '@/lib/api';
	import { clearBufferIfSaved, putDraft, type DraftRecord } from '@/lib/draft-buffer';
	import { retryDelayMs, shouldRetry, type SaveState } from '@/lib/save-state';

	export type SaveSnapshot = { title: string; content: string };

	export type ConflictPrompt = {
		localTitle: string;
		localContent: string;
		serverTitle: string;
		serverContent: string;
		serverRevision: number;
	};

	type ChapterSavesOptions = {
		storyId: string;
		activeId: string;
		draftTitle: string;
		draftContent: string;
		setChapters: Dispatch<SetStateAction<Chapter[]>>;
		setEntries: Dispatch<SetStateAction<BibleEntry[]>>;
		setError: Dispatch<SetStateAction<string>>;
	};

	/**
	 * The chapter save pipeline, extracted from the Studio so the page can keep
	 * composing chrome and tools without owning autosave, retries, or conflicts.
	 *
	 * The returned `draftRef` is deliberately mutable: handlers that outlive a
	 * render (blur, keyboard shortcuts, page hide) must see the latest text.
	 */
	export function useChapterSaves({
		storyId,
		activeId,
		draftTitle,
		draftContent,
		setChapters,
		setEntries,
		setError,
	}: ChapterSavesOptions) {
		const revisionRef = useRef(new Map<string, number>());
		const savedRef = useRef(new Map<string, SaveSnapshot>());
		const saveQueueRef = useRef(new Map<string, Promise<void>>());
		const saveIdRef = useRef(new Map<string, string>());
		const saveTimerRef = useRef<number | null>(null);
		const saveAttemptRef = useRef(0);
		const draftRef = useRef({ chapterId: '', title: '', content: '' });
		const flushRef = useRef<() => Promise<void>>(async () => {});
		const scheduleRetryRef = useRef<(chapterId: string, title: string, content: string) => void>(() => {});

		const [saveState, setSaveState] = useState<SaveState>({ status: 'saved', revision: 1 });
		const [conflict, setConflict] = useState<ConflictPrompt | null>(null);
		const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

		const persistChapter = useCallback((chapterId: string, title: string, content: string) => {
			const previous = saveQueueRef.current.get(chapterId) ?? Promise.resolve();
			const next = previous.catch(() => undefined).then(async () => {
				const saved = savedRef.current.get(chapterId);
				if (saved?.title === title && saved.content === content) {
					saveIdRef.current.delete(chapterId);
					if (chapterId === draftRef.current.chapterId && draftRef.current.title === title && draftRef.current.content === content) {
						setSaveState({ status: 'saved', revision: revisionRef.current.get(chapterId) ?? 1 });
					}
					return;
				}
				const revision = revisionRef.current.get(chapterId);
				if (!revision) return;
				setSaveState({ status: 'saving', revision });
				let saveId = saveIdRef.current.get(chapterId);
				if (!saveId) {
					saveId = typeof crypto !== 'undefined' && 'randomUUID' in crypto
						? crypto.randomUUID()
						: `${Date.now()}-${Math.random().toString(16).slice(2)}`;
					saveIdRef.current.set(chapterId, saveId);
				}
				try {
					const updated = await api.updateChapter(chapterId, title, content, revision, saveId);
					saveIdRef.current.delete(chapterId);
					saveAttemptRef.current = 0;
					revisionRef.current.set(chapterId, updated.revision);
					const savedContent = updated.content ?? content;
					const savedTitle = updated.title;
					savedRef.current.set(chapterId, { title: savedTitle, content: savedContent });
					setChapters((current) => current.map((item) => item.id === chapterId ? { ...item, ...updated, content: savedContent } : item));
					// The buffer is only cleared when it holds exactly what the server
					// stored. Typing during the request keeps it dirty.
					await clearBufferIfSaved(chapterId, { title, content }).catch(() => false);
					const live = draftRef.current;
					if (live.chapterId === chapterId && (live.title !== title || live.content !== content)) {
						setSaveState({ status: 'dirty' });
						setHasUnsavedChanges(true);
					} else {
						setSaveState({ status: 'saved', revision: updated.revision });
						setHasUnsavedChanges(false);
					}
					if (saved && saved.content !== savedContent) {
						setEntries((current) => current.filter((entry) =>
							!(entry.status === 'suggested' && entry.source_chapter_id === chapterId && entry.source_quote && !savedContent.includes(entry.source_quote))
						));
					}
					setError('');
				} catch (cause) {
					if (cause instanceof ApiRequestError && cause.status === 409 && cause.conflict) {
						// Stop retrying. The writer decides which version wins.
						setSaveState({ status: 'conflict', serverRevision: cause.conflict.currentRevision, localContent: content });
						setConflict({
							localTitle: title,
							localContent: content,
							serverTitle: cause.conflict.currentTitle,
							serverContent: cause.conflict.currentContent,
							serverRevision: cause.conflict.currentRevision,
						});
						return;
					}
					const status = cause instanceof ApiRequestError ? cause.status : undefined;
					if (shouldRetry(status)) {
						// The text is already in IndexedDB, so nothing is lost while offline.
						setSaveState({ status: 'offline', pending: true });
						scheduleRetryRef.current(chapterId, title, content);
						return;
					}
					setSaveState({ status: 'error', message: cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'This chapter could not be saved.' });
					setError(cause instanceof Error ? cause.message : 'This chapter could not be saved.');
				}
			});
			saveQueueRef.current.set(chapterId, next);
			return next;
		}, [setChapters, setEntries, setError]);

		// Keep the latest on-screen draft available to callbacks that outlive a render.
		useEffect(() => {
			draftRef.current = { chapterId: activeId, title: draftTitle, content: draftContent };
		}, [activeId, draftTitle, draftContent]);

		useEffect(() => {
			scheduleRetryRef.current = (chapterId, title, content) => {
				const delay = retryDelayMs(saveAttemptRef.current);
				saveAttemptRef.current += 1;
				if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
				saveTimerRef.current = window.setTimeout(() => {
					saveTimerRef.current = null;
					void persistChapter(chapterId, title, content);
				}, delay);
			};
		}, [persistChapter]);

		const flushSaves = useCallback(async () => {
			if (saveTimerRef.current) { window.clearTimeout(saveTimerRef.current); saveTimerRef.current = null; }
			const { chapterId, title, content } = draftRef.current;
			if (!chapterId) return;
			// Persist to the local buffer first: even if the request never completes,
			// the text survives this navigation.
			await putDraft({
				chapterId,
				storyId,
				title,
				content,
				revision: revisionRef.current.get(chapterId) ?? 1,
				updatedAt: Date.now(),
				dirty: true,
			}).catch(() => undefined);
			await persistChapter(chapterId, title, content);
			await (saveQueueRef.current.get(chapterId) ?? Promise.resolve());
		}, [persistChapter, storyId]);

		useEffect(() => {
			flushRef.current = flushSaves;
		}, [flushSaves]);

		// Flush on tab hide and page unload. keepalive requests are only safe for
		// small payloads, so long chapters rely on the IndexedDB buffer instead.
		useEffect(() => {
			const onPageHide = () => { void flushRef.current(); };
			const onVisibility = () => { if (document.hidden) void flushRef.current(); };
			window.addEventListener('pagehide', onPageHide);
			document.addEventListener('visibilitychange', onVisibility);
			return () => {
				window.removeEventListener('pagehide', onPageHide);
				document.removeEventListener('visibilitychange', onVisibility);
				// Studio unmount: a client-side route change skips beforeunload.
				void flushRef.current();
			};
		}, []);

		// Write-ahead log: every keystroke lands in IndexedDB within 250ms.
		useEffect(() => {
			if (!activeId) return;
			const chapterId = activeId;
			const revision = revisionRef.current.get(chapterId) ?? 1;
			const timer = window.setTimeout(() => {
				const record: DraftRecord = {
					chapterId,
					storyId,
					title: draftTitle,
					content: draftContent,
					revision,
					updatedAt: Date.now(),
					dirty: true,
				};
				void putDraft(record).catch(() => undefined);
			}, 250);
			return () => window.clearTimeout(timer);
		}, [activeId, draftTitle, draftContent, storyId]);

		useEffect(() => {
			const saveShortcut = (event: KeyboardEvent) => {
				if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && activeId) {
					event.preventDefault();
					void persistChapter(activeId, draftTitle, draftContent);
				}
			};
			window.addEventListener('keydown', saveShortcut);
			return () => window.removeEventListener('keydown', saveShortcut);
		}, [activeId, draftTitle, draftContent, persistChapter]);

		useEffect(() => {
			if (!activeId) return;
			const saved = savedRef.current.get(activeId);
			if (saved?.title === draftTitle && saved.content === draftContent) return;
			const timer = window.setTimeout(() => {
				void persistChapter(activeId, draftTitle, draftContent);
			}, 800);
			return () => window.clearTimeout(timer);
		}, [activeId, draftTitle, draftContent, persistChapter]);

		useEffect(() => {
			if (!hasUnsavedChanges) return;
			const warnBeforeExit = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
			window.addEventListener('beforeunload', warnBeforeExit);
			return () => window.removeEventListener('beforeunload', warnBeforeExit);
		}, [hasUnsavedChanges]);

		return {
			saveState,
			setSaveState,
			conflict,
			setConflict,
			hasUnsavedChanges,
			setHasUnsavedChanges,
			revisionRef,
			savedRef,
			saveIdRef,
			draftRef,
			persistChapter,
			flushSaves,
		};
	}