'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ChangeEvent } from 'react';
import { Toaster, toast } from 'sonner';
import Link from 'next/link';
import { CaptureDialog, type CaptureMode, type CaptureSelection } from '@/components/wiki/capture-dialog';
import { NameCandidatesPanel } from '@/components/wiki/name-candidates-panel';
import { ChapterRail } from '@/components/studio/chapter-rail';
import { CommandPalette } from '@/components/command-palette';
import { EditorPreferencesMenu } from '@/components/editor-preferences';
import ManuscriptEditor, { type ManuscriptEditorHandle } from '@/components/manuscript-editor';
import { StorySearch } from '@/components/story-search';
import { ConflictDialog } from '@/components/conflict-dialog';
import { ConfirmProvider, useConfirm } from '@/components/confirm-dialog';
import { ApiRequestError, api, type BibleEntry, type Chapter, type ChapterRevisionSummary, type ContinuityFinding, type RevisionDiff, type AIUsage, type Story, type StoryDetails, type StoryArc, type WikiEntity } from '@/lib/api';
import { clearBufferIfSaved, decideDraft, deleteDraft, getDraft, putDraft, type DraftRecord } from '@/lib/draft-buffer';
import { retryDelayMs, saveStatus, shouldRetry, type SaveState } from '@/lib/save-state';
import { getEditorPreferencesSnapshot, getServerEditorPreferencesSnapshot, subscribeEditorPreferences, updateEditorPreferences } from '@/lib/editor-preferences';
import { lineText } from '@/lib/selection';

type Pane = 'notes' | 'findings' | 'mentions' | 'find';
type SaveSnapshot = { title: string; content: string };
type ConflictPrompt = {
	localTitle: string;
	localContent: string;
	serverTitle: string;
	serverContent: string;
	serverRevision: number;
};

const CATEGORY_LABEL: Record<BibleEntry['category'], string> = {
	character: 'Character', location: 'Place', item: 'Important item', world_rule: 'World rule', worldbuilding: 'Worldbuilding', power_system: 'Power system', plot_thread: 'Story thread',
};

function wordCount(text: string) {
	return text.trim() ? text.trim().split(/\s+/).length : 0;
}

export default function StoryStudio({ storyId }: { storyId: string }) {
	return (
		<ConfirmProvider>
			<Toaster position="bottom-right" richColors closeButton />
			<StoryStudioInner storyId={storyId} />
		</ConfirmProvider>
	);
}

function StoryStudioInner({ storyId }: { storyId: string }) {
	const confirm = useConfirm();
	const router = useRouter();
	const searchParams = useSearchParams();
	// Deep links from the wiki: ?chapter=<id>&line=<n> opens that passage.
	const deepChapterId = searchParams.get('chapter');
	const deepLine = Number(searchParams.get('line') ?? '') || 0;
	const jumpedRef = useRef('');
	const editorRef = useRef<ManuscriptEditorHandle>(null);
	const revisionRef = useRef(new Map<string, number>());
	const savedRef = useRef(new Map<string, SaveSnapshot>());
	const saveQueueRef = useRef(new Map<string, Promise<void>>());
	const scanBusyRef = useRef(false);
	const lastScannedWordsRef = useRef(new Map<string, number>());
	const draftEditVersionRef = useRef(0);
	// One idempotency key per unsaved edit; retries reuse it so a lost response
	// cannot create a second revision.
	const saveIdRef = useRef(new Map<string, string>());
	const saveTimerRef = useRef<number | null>(null);
	const saveAttemptRef = useRef(0);
	const draftRef = useRef({ chapterId: '', title: '', content: '' });
	const flushRef = useRef<() => Promise<void>>(async () => {});
	const scheduleRetryRef = useRef<(chapterId: string, title: string, content: string) => void>(() => {});

	const [saveState, setSaveState] = useState<SaveState>({ status: 'saved', revision: 1 });
	const [conflict, setConflict] = useState<ConflictPrompt | null>(null);
	const [recovered, setRecovered] = useState(false);
	const [capture, setCapture] = useState<CaptureSelection | null>(null);
	const editorPreferences = useSyncExternalStore(subscribeEditorPreferences, getEditorPreferencesSnapshot, getServerEditorPreferencesSnapshot);
	const [selection, setSelection] = useState<{ text: string; line: number } | null>(null);
	const [historyDiff, setHistoryDiff] = useState<RevisionDiff | null>(null);
	const [historySelection, setHistorySelection] = useState<number[]>([]);

	const [story, setStory] = useState<StoryDetails | null>(null);
	const [chapters, setChapters] = useState<Chapter[]>([]);
	const [otherStories, setOtherStories] = useState<Story[]>([]);
	const [activeId, setActiveId] = useState('');
	const [draftTitle, setDraftTitle] = useState('');
	const [draftContent, setDraftContent] = useState('');
	const [entries, setEntries] = useState<BibleEntry[]>([]);
	const [wikiEntities, setWikiEntities] = useState<WikiEntity[]>([]);
	const [findings, setFindings] = useState<ContinuityFinding[]>([]);
	const [findingsChapterId, setFindingsChapterId] = useState('');
	const [findingsTargetChapterId, setFindingsTargetChapterId] = useState('');
	const [aiUsage, setAIUsage] = useState<AIUsage | null>(null);
	const [bibleScanStart, setBibleScanStart] = useState(1);
	const [bibleScanEnd, setBibleScanEnd] = useState(1);
	const [bibleScanForce, setBibleScanForce] = useState(false);
	const [bibleScanPending, setBibleScanPending] = useState<Array<{ id: string; revision: number }>>([]);
	const [scanningBible, setScanningBible] = useState(false);
	const [bibleScanMessage, setBibleScanMessage] = useState('');
	const [bibleScanFailed, setBibleScanFailed] = useState(false);
	const [historyOpen, setHistoryOpen] = useState(false);
	const [chapterHistory, setChapterHistory] = useState<ChapterRevisionSummary[]>([]);
	const [historyLoading, setHistoryLoading] = useState(false);
	const [findingFilter, setFindingFilter] = useState<'open' | 'resolved' | 'dismissed' | 'all'>('open');
	const [pane, setPane] = useState<Pane>('notes');
	const [askFocus, setAskFocus] = useState(0);
	const [loading, setLoading] = useState(true);
	const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
	const [checking, setChecking] = useState(false);
	const [checkRetryCountdown, setCheckRetryCountdown] = useState(0);
	const [scanProgress, setScanProgress] = useState<{ scenes_done?: number; scenes_total?: number; scenes_failed?: number } | null>(null);
	const [lastScan, setLastScan] = useState<{ chapterId: string; revision: number } | null>(null);
	const [focusMode, setFocusMode] = useState(false);
	const [paneOpen, setPaneOpen] = useState(true);
	const [arcs, setArcs] = useState<StoryArc[]>([]);
	const [paneWidth, setPaneWidth] = useState(() => {
		if (typeof window === 'undefined') return 372;
		const stored = Number(window.localStorage.getItem('stillroom:pane-width'));
		return Number.isFinite(stored) && stored > 0 ? Math.min(Math.max(stored, 320), 720) : 372;
	});
	const [error, setError] = useState('');
	const [notice, setNotice] = useState('');

	const activeChapter = chapters.find((chapter) => chapter.id === activeId) ?? null;
	const activeChapterId = activeChapter?.id;
	const activeChapterRevision = activeChapter?.revision;
	const words = wordCount(draftContent);
	const earlierChapters = chapters.filter((chapter) => chapter.chapter_number < (activeChapter?.chapter_number ?? 0));
	const earlierIndexedCount = earlierChapters.filter((chapter) => chapter.index_status === 'indexed').length;
	const earlierChaptersReady = earlierChapters.length > 0 && earlierIndexedCount === earlierChapters.length;
	const currentFindings = useMemo(() => findingsChapterId === findingsTargetChapterId ? findings : [], [findings, findingsChapterId, findingsTargetChapterId]);
	const visibleFindings = useMemo(() => currentFindings.filter((finding) => findingFilter === 'all' || finding.review_status === findingFilter), [currentFindings, findingFilter]);

	/** Merge the server chapter with any local write-ahead copy. */
	const resolveChapterDraft = useCallback(async (fullChapter: Chapter) => {
		const server = {
			revision: fullChapter.revision,
			title: fullChapter.title,
			content: fullChapter.content ?? '',
		};
		let buffer: DraftRecord | undefined;
		try {
			buffer = await getDraft(fullChapter.id);
		} catch {
			buffer = undefined;
		}
		const decision = decideDraft(server, buffer);
		if (decision.action === 'server') {
			if (buffer) await deleteDraft(fullChapter.id).catch(() => undefined);
			return { title: server.title, content: server.content, recovered: false, conflict: null };
		}
		if (decision.action === 'use-local') {
			return { title: buffer!.title, content: buffer!.content, recovered: true, conflict: null };
		}
		// A revision mismatch is never resolved silently: show the local text and
		// let the writer choose between it and the saved version.
		return {
			title: buffer!.title,
			content: buffer!.content,
			recovered: false,
			conflict: {
				localTitle: buffer!.title,
				localContent: buffer!.content,
				serverTitle: server.title,
				serverContent: server.content,
				serverRevision: server.revision,
			} satisfies ConflictPrompt,
		};
	}, []);

	const refreshBible = useCallback(async () => {
		try {
			const [bible, entities] = await Promise.all([api.bible(storyId), api.entities(storyId).catch(() => null)]);
			setEntries(bible);
			if (entities) setWikiEntities(entities);
		} catch { /* Keep the draft available during brief reconnects. */ }
	}, [storyId]);

	useEffect(() => {
		let alive = true;
		async function load() {
			try {
				const [storyData, bible, entityList, storyList, arcList, usage] = await Promise.all([
					api.story(storyId),
					api.bible(storyId),
					api.entities(storyId).catch(() => [] as WikiEntity[]),
					api.stories(),
					// Arcs are optional furniture: an empty list must never block the draft.
					api.arcs(storyId).catch(() => [] as StoryArc[]),
					api.aiUsage(storyId).catch(() => null),
				]);
				if (!alive) return;
				setStory(storyData);
				setAIUsage(usage);
				setChapters(storyData.chapters);
				setArcs(arcList);
				setEntries(bible);
				setWikiEntities(entityList);
				setOtherStories(storyList.filter((item) => item.id !== storyId));
				setBibleScanStart(1);
				setBibleScanEnd(storyData.chapters.at(-1)?.chapter_number ?? 1);
				const rememberedId = window.sessionStorage.getItem(`stillroom-active-chapter:${storyId}`);
				const initialChapter =
					storyData.chapters.find((chapter) => chapter.id === deepChapterId)
					?? storyData.chapters.find((chapter) => chapter.id === rememberedId)
					?? storyData.chapters[0];
				if (initialChapter) {
					const fullChapter = await api.chapter(initialChapter.id);
					if (!alive) return;
					const resolved = await resolveChapterDraft(fullChapter);
					if (!alive) return;
					setActiveId(initialChapter.id);
					setFindingsTargetChapterId(initialChapter.id);
					setHasUnsavedChanges(resolved.conflict !== null);
					setRecovered(resolved.recovered);
					setConflict(resolved.conflict);
					revisionRef.current.set(fullChapter.id, fullChapter.revision);
					setSaveState(resolved.conflict
						? { status: 'conflict', serverRevision: fullChapter.revision, localContent: resolved.content }
						: { status: 'saved', revision: fullChapter.revision });
					setDraftTitle(resolved.title);
					setDraftContent(resolved.content);
					setChapters((current) => current.map((chapter) => chapter.id === fullChapter.id ? fullChapter : chapter));
					for (const chapter of storyData.chapters) revisionRef.current.set(chapter.id, chapter.revision);
					savedRef.current.set(initialChapter.id, { title: fullChapter.title, content: fullChapter.content ?? '' });
					window.sessionStorage.setItem(`stillroom-active-chapter:${storyId}`, initialChapter.id);
				}
			} catch (cause) {
				if (!alive) return;
				if (cause instanceof Error && cause.message.includes('(401)')) router.replace('/login');
				else setError(cause instanceof Error ? cause.message : 'This story could not be opened.');
			} finally {
				if (alive) setLoading(false);
			}
		}
		void load();
		return () => { alive = false; };
	}, [storyId, router, resolveChapterDraft, deepChapterId]);

	// Once the linked chapter is on screen, put the caret on the cited line.
	useEffect(() => {
		if (!deepLine || !activeId || !editorRef.current) return;
		const marker = `${activeId}:${deepLine}`;
		if (jumpedRef.current === marker) return;
		if (!lineText(draftContent, deepLine)) return;
		jumpedRef.current = marker;
		editorRef.current.focusLine(deepLine);
	}, [activeId, deepLine, draftContent]);

	useEffect(() => {
		if (!hasUnsavedChanges) return;
		const warnBeforeExit = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
		window.addEventListener('beforeunload', warnBeforeExit);
		return () => window.removeEventListener('beforeunload', warnBeforeExit);
	}, [hasUnsavedChanges]);

	useEffect(() => {
		if (checkRetryCountdown <= 0) return;
		const timer = window.setTimeout(() => setCheckRetryCountdown((remaining) => Math.max(0, remaining - 1)), 1000);
		return () => window.clearTimeout(timer);
	}, [checkRetryCountdown]);

	useEffect(() => {
		if (!activeChapterId) return;
		const chapterId = activeChapterId;
		const key = `stillroom-scan:${storyId}:${chapterId}`;
		const jobId = window.sessionStorage.getItem(key);
		if (!jobId) return;
		const activeJobId = jobId;
		let alive = true;
		async function resume() {
			setChecking(true);
			setNotice('Resuming the continuity check that was running before the page reloaded.');
			try {
				let completed = false;
				for (let attempt = 0; attempt < 600; attempt += 1) {
					await new Promise<void>((resolve) => window.setTimeout(resolve, 1000));
					if (!alive) return;
					const job = await api.job(activeJobId);
					setScanProgress(job.progress);
					if (job.status === 'succeeded') { completed = true; break; }
					if (job.status === 'cancelled' || job.status === 'dead') throw new Error(job.last_error ?? 'The continuity check did not finish.');
				}
				if (!alive) return;
				if (!completed) throw new Error('The continuity check is still running. Its result will be saved when it finishes.');
				const latest = await api.latestScan(chapterId);
				if (!alive) return;
				setFindingsTargetChapterId(chapterId);
				setFindingsChapterId(chapterId);
				setFindings(latest.findings);
				setLastScan(latest.scan ? { chapterId, revision: latest.scan.chapter_revision } : null);
				setNotice(latest.scan?.scenes_failed
					? `The background check finished, but ${latest.scan.scenes_failed} scene${latest.scan.scenes_failed === 1 ? '' : 's'} could not be checked.`
					: latest.findings.length ? 'The background check finished. A few details may be worth another look.' : 'The background check finished with no clear conflicts.');
			} catch (cause) {
				if (alive) setError(cause instanceof Error ? cause.message : 'The background check could not be resumed.');
			} finally {
				if (alive) { setChecking(false); setScanProgress(null); }
				window.sessionStorage.removeItem(key);
			}
		}
		void resume();
		return () => { alive = false; };
	}, [activeChapterId, storyId]);

	useEffect(() => {
		if (!activeChapterId || activeChapterRevision === undefined || findingsTargetChapterId !== activeChapterId) return;
		let alive = true;
		api.latestScan(activeChapterId).then((result) => {
			if (!alive) return;
			setFindingsChapterId(activeChapterId);
			setFindings(result.scan?.chapter_revision === activeChapterRevision ? result.findings : []);
			setLastScan(result.scan ? { chapterId: activeChapterId, revision: result.scan.chapter_revision } : null);
			lastScannedWordsRef.current.set(activeChapterId, result.scan?.chapter_word_count ?? 0);
		}).catch(() => { if (alive) { setFindingsChapterId(activeChapterId); setFindings([]); setLastScan(null); } });
		return () => { alive = false; };
	}, [activeChapterId, activeChapterRevision, findingsTargetChapterId]);

	async function changeFindingChapter(chapterId: string) {
		if (!chapterId) return;
		setFindingsTargetChapterId(chapterId);
		setFindingsChapterId('');
		setFindings([]);
		try {
			const latest = await api.latestScan(chapterId);
			setFindingsChapterId(chapterId);
			setFindings(latest.findings);
			setLastScan(latest.scan ? { chapterId, revision: latest.scan.chapter_revision } : null);
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'Continuity history could not be loaded.'); }
	}

	useEffect(() => {
		const indexing = chapters.some((chapter) => chapter.index_status === 'pending' || chapter.index_status === 'indexing');
		if (!indexing && !bibleScanPending.length) return;
		let alive = true;
		const timer = window.setInterval(async () => {
			try {
				const latest = await api.storyIndexStatus(storyId);
				if (!alive) return;
				setChapters((current) => current.map((chapter) => {
					const updated = latest.chapters.find((item) => item.id === chapter.id);
					return updated ? { ...chapter, index_status: updated.index_status, index_error: updated.index_error, bible_scan_revision: updated.bible_scan_revision } : chapter;
				}));
				const outcomes = bibleScanPending.map((target) => {
					const updated = latest.chapters.find((chapter) => chapter.id === target.id);
					if (!updated) return 'failed';
					if (updated.revision !== target.revision) return 'changed';
					if (updated.bible_scan_error) return 'failed';
					return updated.bible_scan_revision === target.revision ? 'complete' : 'pending';
				});
				if (bibleScanPending.length && outcomes.every((outcome) => outcome !== 'pending')) {
					const failedCount = outcomes.filter((outcome) => outcome === 'failed').length;
					const changedCount = outcomes.filter((outcome) => outcome === 'changed').length;
					const firstScanError = bibleScanPending
						.map((target) => latest.chapters.find((chapter) => chapter.id === target.id)?.bible_scan_error)
						.find(Boolean);
					setBibleScanPending([]);
					setBibleScanFailed(failedCount > 0);
					setBibleScanMessage(failedCount
						? `${failedCount} ${failedCount === 1 ? 'chapter scan failed' : 'chapter scans failed'}. ${firstScanError ?? 'Try again later.'}`
						: changedCount
							? `Scan finished, but ${changedCount} chapter ${changedCount === 1 ? 'changed' : 'chapters changed'} while it was running and was skipped. Scan again to review the latest text.`
							: 'Story Bible scan complete. Suggestions have been refreshed.');
					void refreshBible();
				}
			} catch { /* A later poll will retry. */ }
		}, 3500);
		return () => { alive = false; window.clearInterval(timer); };
	}, [chapters, storyId, refreshBible, bibleScanPending]);

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
	}, []);

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

	/** Guarded navigation: flush, then confirm if the save did not land. */
	const go = useCallback(async (href: string) => {
		await flushSaves();
		const chapterId = draftRef.current.chapterId;
		const saved = chapterId ? savedRef.current.get(chapterId) : undefined;
		const unsaved = Boolean(chapterId) && (!saved || saved.title !== draftRef.current.title || saved.content !== draftRef.current.content);
		if (unsaved) {
			const leave = await confirm({
				title: 'Leave with unsaved changes?',
				description: 'Your text is kept in this browser and will be recovered next time you open this chapter.',
				confirmLabel: 'Leave anyway',
			});
			if (!leave) return;
		}
		router.push(href);
	}, [flushSaves, confirm, router]);

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
		if (!activeChapterId) return;
		const chapterId = activeChapterId;
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
	}, [activeChapterId, draftTitle, draftContent, storyId]);


	useEffect(() => {
		const saveShortcut = (event: KeyboardEvent) => {
			if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && activeChapterId) {
				event.preventDefault();
				void persistChapter(activeChapterId, draftTitle, draftContent);
			}
		};
		window.addEventListener('keydown', saveShortcut);
		return () => window.removeEventListener('keydown', saveShortcut);
	}, [activeChapterId, draftTitle, draftContent, persistChapter]);

	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent) => {
			if ((event.metaKey || event.ctrlKey) && event.key === '.') {
				event.preventDefault();
				setPaneOpen((value) => !value);
			}
			if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'w') {
				event.preventDefault();
				void go(`/stories/${storyId}/wiki`);
			}
		};
		window.addEventListener('keydown', onKeyDown);
		return () => window.removeEventListener('keydown', onKeyDown);
	}, [go, storyId]);

	useEffect(() => {
		if (!activeChapterId) return;
		const saved = savedRef.current.get(activeChapterId);
		if (saved?.title === draftTitle && saved.content === draftContent) return;
		const timer = window.setTimeout(() => {
			void persistChapter(activeChapterId, draftTitle, draftContent);
		}, 800);
		return () => window.clearTimeout(timer);
	}, [activeChapterId, draftTitle, draftContent, persistChapter]);

	const selectChapter = useCallback(async (chapter: Chapter) => {
		if (activeChapter) {
			await persistChapter(activeChapter.id, draftTitle, draftContent);
			const saved = savedRef.current.get(activeChapter.id);
			if (!saved || saved.title !== draftTitle || saved.content !== draftContent) return;
		}
		const fullChapter = await api.chapter(chapter.id);
		const resolved = await resolveChapterDraft(fullChapter);
		revisionRef.current.set(chapter.id, fullChapter.revision);
		savedRef.current.set(chapter.id, { title: fullChapter.title, content: fullChapter.content ?? '' });
		setChapters((current) => current.map((item) => item.id === chapter.id ? fullChapter : item));
		setActiveId(chapter.id);
		setFindingsTargetChapterId(chapter.id);
		setHasUnsavedChanges(resolved.conflict !== null);
		setRecovered(resolved.recovered);
		setConflict(resolved.conflict);
		setSaveState(resolved.conflict
			? { status: 'conflict', serverRevision: fullChapter.revision, localContent: resolved.content }
			: { status: 'saved', revision: fullChapter.revision });
		window.sessionStorage.setItem(`stillroom-active-chapter:${storyId}`, chapter.id);
		setDraftTitle(resolved.title);
		setDraftContent(resolved.content);
		setError('');
	}, [activeChapter, draftTitle, draftContent, persistChapter, storyId, resolveChapterDraft]);

	async function addChapter() {
		try {
			if (activeChapter) {
				await persistChapter(activeChapter.id, draftTitle, draftContent);
				const saved = savedRef.current.get(activeChapter.id);
				if (!saved || saved.title !== draftTitle || saved.content !== draftContent) return;
			}
			const chapter = await api.createChapter(storyId);
			revisionRef.current.set(chapter.id, chapter.revision);
			savedRef.current.set(chapter.id, { title: chapter.title, content: chapter.content ?? '' });
			setChapters((current) => [...current, chapter]);
			setActiveId(chapter.id); setDraftTitle(chapter.title); setDraftContent(''); setFindings([]);
			setFindingsTargetChapterId(chapter.id); setHasUnsavedChanges(false);
			window.sessionStorage.setItem(`stillroom-active-chapter:${storyId}`, chapter.id);
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'Chapter could not be created.'); }
	}

	async function reorderChapter(chapterId: string, direction: -1 | 1) {
		const currentIndex = chapters.findIndex((item) => item.id === chapterId);
		const destinationIndex = currentIndex + direction;
		if (currentIndex < 0 || destinationIndex < 0 || destinationIndex >= chapters.length) return;
		const reordered = [...chapters];
		[reordered[currentIndex], reordered[destinationIndex]] = [reordered[destinationIndex], reordered[currentIndex]];
		try {
			const result = await api.reorderChapters(storyId, reordered.map((item) => item.id));
			setChapters(result.chapters);
			setFindings([]);
			setNotice('Chapter order updated. Run a new continuity check to refresh earlier chapter comparisons.');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'Chapter order could not be changed.'); }
	}

	async function moveActiveChapter(destinationStoryId: string) {
		if (!activeChapter || destinationStoryId === storyId) return;
		await persistChapter(activeChapter.id, draftTitle, draftContent);
		const saved = savedRef.current.get(activeChapter.id);
		if (!saved || saved.title !== draftTitle || saved.content !== draftContent) return;
		if (!await confirm({
			title: 'Move this chapter?',
			description: `“${activeChapter.title}” will move to the other story and this story's continuity checks will be cleared.`,
			confirmLabel: 'Move chapter',
		})) return;
		try {
			await api.moveChapter(activeChapter.id, destinationStoryId);
			window.sessionStorage.removeItem(`stillroom-active-chapter:${storyId}`);
			router.push(`/stories/${destinationStoryId}`);
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'Chapter could not be moved.'); }
	}

	async function openChapterHistory() {
		if (!activeChapter) return;
		setHistoryOpen(true);
		setHistorySelection([]);
		setHistoryDiff(null);
		setHistoryLoading(true);
		try { setChapterHistory(await api.chapterRevisions(activeChapter.id)); }
		catch (cause) { setError(cause instanceof Error ? cause.message : 'Version history could not be loaded.'); }
		finally { setHistoryLoading(false); }
	}

	async function saveCheckpoint() {
		if (!activeChapter) return;
		try {
			if (hasUnsavedChanges) await flushSaves();
			await api.checkpointChapter(activeChapter.id);
			setChapterHistory(await api.chapterRevisions(activeChapter.id));
			toast.success('Checkpoint saved. It will not be pruned.');
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'The checkpoint could not be saved.');
		}
	}

	async function compareVersions(first: number, second: number) {
		if (!activeChapter) return;
		const older = Math.min(first, second);
		const newer = Math.max(first, second);
		try {
			setHistoryDiff(await api.diffRevisions(activeChapter.id, older, newer));
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'Those versions could not be compared.');
		}
	}

	async function restoreChapterHistory(revision: ChapterRevisionSummary) {
		if (!activeChapter || !await confirm({
			title: 'Restore this version?',
			description: `Version ${revision.revision_number} replaces the text in the editor. Your current draft is pinned in history first.`,
			confirmLabel: 'Restore version',
		})) return;
		try {
			if (hasUnsavedChanges) await persistChapter(activeChapter.id, draftTitle, draftContent);
			const saved = savedRef.current.get(activeChapter.id);
			if (!saved || saved.title !== draftTitle || saved.content !== draftContent) throw new Error('The current draft could not be saved before restoring.');
			const updated = await api.restoreChapterRevision(activeChapter.id, revision.revision_number);
			revisionRef.current.set(updated.id, updated.revision);
			savedRef.current.set(updated.id, { title: updated.title, content: updated.content ?? '' });
			setDraftTitle(updated.title); setDraftContent(updated.content ?? '');
			setHasUnsavedChanges(false);
			setFindingsTargetChapterId(updated.id); setFindingsChapterId('');
			setChapters((current) => current.map((item) => item.id === updated.id ? updated : item));
			setHistoryOpen(false); setNotice(`Restored version ${revision.revision_number}.`);
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'That version could not be restored.'); }
	}

	async function keepMyVersion() {
		if (!conflict || !activeChapter) return;
		const chapterId = activeChapter.id;
		setConflict(null);
		revisionRef.current.set(chapterId, conflict.serverRevision);
		savedRef.current.set(chapterId, { title: conflict.serverTitle, content: conflict.serverContent });
		saveIdRef.current.delete(chapterId);
		await persistChapter(chapterId, conflict.localTitle, conflict.localContent);
		if (revisionRef.current.get(chapterId) !== conflict.serverRevision) toast.success('Your version was saved.');
	}

	async function reloadSavedVersion() {
		if (!conflict || !activeChapter) return;
		const ok = await confirm({
			title: 'Discard your local version?',
			description: 'The saved version replaces the text in this editor. Your local copy stays in this browser until you save again.',
			confirmLabel: 'Load saved version',
			destructive: true,
		});
		if (!ok) return;
		setDraftTitle(conflict.serverTitle);
		setDraftContent(conflict.serverContent);
		savedRef.current.set(activeChapter.id, { title: conflict.serverTitle, content: conflict.serverContent });
		revisionRef.current.set(activeChapter.id, conflict.serverRevision);
		await deleteDraft(activeChapter.id).catch(() => undefined);
		saveIdRef.current.delete(activeChapter.id);
		setConflict(null);
		setHasUnsavedChanges(false);
		setSaveState({ status: 'saved', revision: conflict.serverRevision });
	}

	function copyChangesForMerge() {
		setConflict(null);
		setSaveState({ status: 'dirty' });
		setHasUnsavedChanges(true);
		setNotice('Both versions are in this editor. Merge them by hand, then save.');
	}

	async function deleteChapter(chapter: Chapter) {
		if (!await confirm({
			title: 'Move this chapter to the trash?',
			description: `“${chapter.title}” can be restored from the trash for 30 days.`,
			confirmLabel: 'Move to trash',
			destructive: true,
		})) return;
		const deletedIndex = chapters.findIndex((item) => item.id === chapter.id);
		if (activeChapter?.id === chapter.id) {
			await persistChapter(chapter.id, draftTitle, draftContent);
			const saved = savedRef.current.get(chapter.id);
			if (!saved || saved.title !== draftTitle || saved.content !== draftContent) return;
		}
		try {
			const result = await api.deleteChapter(chapter.id);
			setChapters(result.chapters);
			revisionRef.current.delete(chapter.id);
			savedRef.current.delete(chapter.id);
			const lastChapter = result.chapters.at(-1);
			const maxNumber = lastChapter?.chapter_number ?? 1;
			setBibleScanStart((current) => Math.min(current, maxNumber));
			setBibleScanEnd((current) => Math.min(Math.max(current, bibleScanStart), maxNumber));
			if (activeChapter?.id === chapter.id) {
				const nextChapter = result.chapters[Math.min(deletedIndex, result.chapters.length - 1)];
				setFindings([]);
				if (nextChapter) {
					window.sessionStorage.setItem(`stillroom-active-chapter:${storyId}`, nextChapter.id);
					try {
						const fullChapter = await api.chapter(nextChapter.id);
						revisionRef.current.set(nextChapter.id, fullChapter.revision);
						savedRef.current.set(nextChapter.id, { title: fullChapter.title, content: fullChapter.content ?? '' });
						setChapters((current) => current.map((item) => item.id === nextChapter.id ? fullChapter : item));
						setActiveId(nextChapter.id);
						setFindingsTargetChapterId(nextChapter.id);
						setHasUnsavedChanges(false);
						setDraftTitle(fullChapter.title);
						setDraftContent(fullChapter.content ?? '');
					} catch {
						setActiveId('');
						setFindingsTargetChapterId('');
						setDraftTitle('');
						setDraftContent('');
						setError('Chapter deleted, but the next chapter could not be loaded. Refresh to reopen it.');
					}
				} else {
					setActiveId(''); setFindingsTargetChapterId(''); setDraftTitle(''); setDraftContent(''); setHasUnsavedChanges(false);
					window.sessionStorage.removeItem(`stillroom-active-chapter:${storyId}`);
				}
			}
			await refreshBible();
			setNotice('Chapter moved to the trash. Remaining chapters were renumbered.');
			await deleteDraft(chapter.id).catch(() => undefined);
			saveIdRef.current.delete(chapter.id);
			setError('');
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'The chapter could not be deleted.');
		}
	}

	async function importManuscript(event: ChangeEvent<HTMLInputElement>) {
		const file = event.target.files?.[0];
		event.target.value = '';
		if (!file) return;
		try {
			if (activeChapter) {
				await persistChapter(activeChapter.id, draftTitle, draftContent);
				const saved = savedRef.current.get(activeChapter.id);
				if (!saved || saved.title !== draftTitle || saved.content !== draftContent) return;
			}
			const result = await api.importManuscript(storyId, file.name, await file.text());
			for (const chapter of result.chapters) {
				revisionRef.current.set(chapter.id, chapter.revision);
			}
			setChapters((current) => [...current, ...result.chapters]);
			if (result.chapters[0]) await selectChapter(result.chapters[0]);
			setNotice('Manuscript imported. Story memory is updating in the background.');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'The manuscript could not be imported.'); }
	}

	async function exportManuscript() {
		if (!story) return;
		if (activeChapter) await persistChapter(activeChapter.id, draftTitle, draftContent);
		const chaptersToExport = await Promise.all(chapters.map(async (chapter) => {
			if (chapter.id === activeId) return { ...chapter, title: draftTitle, content: draftContent };
			return api.chapter(chapter.id);
		}));
		const body = ['# ' + story.title, '', ...chaptersToExport.sort((a, b) => a.chapter_number - b.chapter_number).flatMap((chapter) => [
			'## Chapter ' + chapter.chapter_number + ': ' + chapter.title, '', chapter.content ?? '', '',
		])].join('\n');
		const url = URL.createObjectURL(new Blob([body], { type: 'text/markdown;charset=utf-8' }));
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = (story.title || 'manuscript').replace(/[\\/:*?"<>|]+/g, '-').trim() + '.md';
		anchor.click();
		window.setTimeout(() => URL.revokeObjectURL(url), 1000);
	}

	async function changeStorySetting(changes: { external_analysis_enabled?: boolean; scan_interval_words?: number; monthly_ai_budget?: number }): Promise<boolean> {
		if (!story) return false;
		try { setStory({ ...story, ...await api.updateStory(storyId, changes) }); setError(''); return true; }
		catch (cause) { setError(cause instanceof Error ? cause.message : 'Story settings could not be saved.'); return false; }
	}

	async function scanBibleRange() {
		if (!chapters.length || scanningBible || bibleScanPending.length) return;
		setScanningBible(true);
		setBibleScanMessage('');
		setBibleScanFailed(false);
		setError('');
		try {
			const result = await api.scanBibleRange(storyId, bibleScanStart, bibleScanEnd, bibleScanForce);
			setBibleScanPending(result.scheduled_chapters);
			setBibleScanMessage(result.scheduled_count
				? `Scanning ${result.scheduled_count} ${result.scheduled_count === 1 ? 'chapter' : 'chapters'}; ${result.skipped_count} skipped. No scans run automatically when you edit.`
				: `Nothing to scan. All ${result.skipped_count} chapters in this range are already up to date.`);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'The Story Bible scan could not be started.');
		} finally {
			setScanningBible(false);
		}
	}

	async function cancelScan(chapterId: string) {
		const jobId = window.sessionStorage.getItem(`stillroom-scan:${storyId}:${chapterId}`);
		if (!jobId) return;
		try { await api.cancelJob(jobId); setNotice('Cancelling after the current scene…'); }
		catch (cause) { setError(cause instanceof Error ? cause.message : 'The check could not be cancelled.'); }
	}

	async function retryIndex() {
		if (!activeChapter) return;
		try {
			await api.retryChapterIndex(activeChapter.id);
			setChapters((current) => current.map((item) => item.id === activeChapter.id ? { ...item, index_status: 'pending', index_error: null } : item));
			setError('');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'Story memory could not be restarted.'); }
	}

	const showStoredScan = useCallback(async (chapterId: string, revision: number | undefined) => {
		if (revision === undefined) return false;
		try {
			const latest = await api.latestScan(chapterId);
			if (!latest.scan || latest.scan.chapter_revision !== revision) return false;
			setFindingsTargetChapterId(chapterId);
			setFindingsChapterId(chapterId);
			setFindings(latest.findings);
			setLastScan({ chapterId, revision: latest.scan.chapter_revision });
			lastScannedWordsRef.current.set(chapterId, latest.scan.chapter_word_count);
			return true;
		} catch { return false; }
	}, []);

	async function runCheck(automatic = false, force = false) {
		if (!activeChapter || scanBusyRef.current) return;
		const chapterId = activeChapter.id;
		let scannedRevision: number | undefined;
		scanBusyRef.current = true; setChecking(true); setError(''); setNotice('');
		try {
			if (savedRef.current.get(chapterId)?.content !== draftContent || savedRef.current.get(chapterId)?.title !== draftTitle) {
				await persistChapter(chapterId, draftTitle, draftContent);
			}
			const saved = savedRef.current.get(chapterId);
			if (!saved || saved.content !== draftContent || saved.title !== draftTitle) {
				throw new Error('The latest draft could not be saved, so no check was run.');
			}
			let ready = false;
			for (let attempt = 0; attempt < 30; attempt += 1) {
				const status = await api.chapterStatus(chapterId);
				setChapters((current) => current.map((item) => item.id === status.id ? { ...item, ...status } : item));
				if (status.index_status === 'indexed') { ready = true; break; }
				if (status.index_status === 'failed') throw new Error('Story memory could not be updated. Check the local Ollama embedding service.');
				await new Promise<void>((resolve) => window.setTimeout(resolve, 500));
			}
			if (!ready) throw new Error('Story memory is taking longer than expected. Try the check again shortly.');
			scannedRevision = revisionRef.current.get(chapterId);
			const queued = await api.queueScan(chapterId, force);
			window.sessionStorage.setItem(`stillroom-scan:${storyId}:${chapterId}`, queued.job_id);
			setNotice('The check is running in the background. You can keep writing.');
			let completed = false;
			for (let attempt = 0; attempt < 600; attempt += 1) {
				await new Promise<void>((resolve) => window.setTimeout(resolve, 1000));
				const job = await api.job(queued.job_id);
				setScanProgress(job.progress);
				if (job.status === 'succeeded') { completed = true; break; }
				if (job.status === 'cancelled') throw new Error('The continuity check was cancelled.');
				if (job.status === 'dead') throw new Error(job.last_error ?? 'The continuity check failed.');
			}
			if (!completed) throw new Error('The continuity check is taking longer than expected. Its result will still be saved when it finishes.');
			const latest = await api.latestScan(chapterId);
			setFindingsTargetChapterId(chapterId);
			setFindingsChapterId(chapterId);
			setFindings(latest.findings);
			setLastScan(latest.scan ? { chapterId, revision: latest.scan.chapter_revision } : null);
			lastScannedWordsRef.current.set(chapterId, latest.scan?.chapter_word_count ?? words);
			setNotice(automatic
				? 'Your scheduled continuity check is complete.'
				: latest.scan?.scenes_failed
					? `${latest.scan.scenes_failed} scene${latest.scan.scenes_failed === 1 ? '' : 's'} could not be checked; the rest of the scan is saved. Run again to retry them.`
					: latest.scan?.chapter_revision === revisionRef.current.get(chapterId)
						? latest.findings.length ? 'A few details may be worth another look.' : 'No clear continuity conflicts found in earlier chapters.'
						: 'The chapter changed while it was being checked. Run the check again to review the latest text.');
		} catch (cause) {
			// The provider may have answered and saved the scan even when the browser
			// lost the response, so look for a stored result before reporting a failure.
			let recovered = await showStoredScan(chapterId, scannedRevision ?? revisionRef.current.get(chapterId));
			for (let attempt = 0; !recovered && attempt < 3; attempt += 1) {
				await new Promise<void>((resolve) => window.setTimeout(resolve, 1500));
				recovered = await showStoredScan(chapterId, scannedRevision ?? revisionRef.current.get(chapterId));
			}
			if (recovered) {
				setNotice('The check finished and its findings were saved, but the browser lost the response. They are shown below.');
			} else {
				if (cause instanceof ApiRequestError && cause.status === 429 && !cause.message.includes('daily free-model allowance')) {
					setCheckRetryCountdown(cause.retryAfterSeconds ?? 8);
				}
				setError(cause instanceof Error ? cause.message.replace(/ \(\d+\)$/, '') : 'The continuity check could not be completed.');
			}
		} finally {
			scanBusyRef.current = false;
			setChecking(false);
			setScanProgress(null);
			window.sessionStorage.removeItem(`stillroom-scan:${storyId}:${chapterId}`);
		}
	}

	useEffect(() => {
		if (!story?.external_analysis_enabled || !activeChapter || activeChapter.index_status !== 'indexed' || !earlierChaptersReady || story.scan_interval_words <= 0) return;
		const last = lastScannedWordsRef.current.get(activeChapter.id) ?? 0;
		if (words - last >= story.scan_interval_words) void runCheck(true);
		// Checking is intentionally tied to the selected chapter's word-count interval.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [words, activeChapter?.id, activeChapter?.index_status, earlierChaptersReady, story?.scan_interval_words, story?.external_analysis_enabled]);

	async function assignArc(chapterId: string, arcId: string | null) {
		const previous = chapters;
		setChapters((current) => current.map((chapter) => (chapter.id === chapterId ? { ...chapter, arc_id: arcId } : chapter)));
		try {
			await api.assignArc(storyId, arcId, [chapterId]);
			setArcs(await api.arcs(storyId));
		} catch (cause) {
			setChapters(previous);
			toast.error(cause instanceof Error ? cause.message : 'That chapter could not be moved.');
		}
	}

	async function createArc(name: string) {
		try {
			await api.createArc(storyId, name);
			setArcs(await api.arcs(storyId));
			toast.success(`“${name}” added. Assign chapters from the rail.`);
		} catch (cause) {
			toast.error(cause instanceof Error ? cause.message : 'That arc could not be created.');
		}
	}

	async function openBibleSource(entry: BibleEntry) {
		if (!entry.source_chapter_id) return;
		const source = chapters.find((item) => item.id === entry.source_chapter_id);
		if (!source) return;
		try {
			const full = await api.chapter(source.id);
			await selectChapter(source);
			if (!entry.source_quote) return;
			window.setTimeout(() => {
				const editor = editorRef.current;
				const offset = (full.content ?? '').indexOf(entry.source_quote ?? '');
				if (!editor || offset < 0) return;
				editor.focusRange(offset, offset + (entry.source_quote?.length ?? 0));
			}, 0);
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'Source chapter could not be opened.'); }
	}

	async function setThread(entry: BibleEntry, state: 'open' | 'resolved') {
		try {
			const updated = await api.updateThread(entry.id, state);
			setEntries((current) => current.map((item) => item.id === entry.id ? updated : item));
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'The thread status could not be changed.'); }
	}

	async function markIntentional(finding: ContinuityFinding) {
		try {
			await api.markIntentional(finding.id);
			setFindings((current) => current.map((item) => item.id === finding.id ? { ...item, intentional: true, review_status: 'dismissed' } : item));
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'The flag could not be updated.'); }
	}

	async function reviewFinding(finding: ContinuityFinding, reviewStatus: 'open' | 'resolved' | 'dismissed') {
		try {
			const updated = await api.reviewFinding(finding.id, reviewStatus);
			setFindings((current) => current.map((item) => item.id === finding.id ? { ...item, ...updated } : item));
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'Finding status could not be changed.'); }
	}

	function locateLine(lineNumber: number) {
		editorRef.current?.focusLine(lineNumber);
	}

	async function openSearchHit(chapterId: string, line: number) {
		const target = chapters.find((item) => item.id === chapterId);
		if (!target) return;
		await selectChapter(target);
		window.setTimeout(() => {
			editorRef.current?.focusLine(line);
			setPaneOpen(false);
		}, 60);
	}

	async function openFindingLine(finding: ContinuityFinding) {
		if (findingsTargetChapterId !== activeId) {
			const target = chapters.find((item) => item.id === findingsTargetChapterId);
			if (!target) return;
			await selectChapter(target);
		}
		window.setTimeout(() => locateLine(finding.draft_line), 0);
	}

	function openEntity(entityId: string) {
		void go(`/stories/${storyId}/wiki/${entityId}`);
	}

	function handleFindingAction(finding: ContinuityFinding, action: 'resolve' | 'dismiss' | 'intentional') {
		if (action === 'intentional') void markIntentional(finding);
		else void reviewFinding(finding, action === 'resolve' ? 'resolved' : 'dismissed');
	}

	async function openFindingEvidence(finding: ContinuityFinding) {
		if (!finding.earlier_chapter_id) return;
		const target = chapters.find((chapter) => chapter.id === finding.earlier_chapter_id);
		if (!target) return;
		try {
			await selectChapter(target);
			window.setTimeout(async () => {
				try {
					const full = await api.chapter(target.id);
					const offset = (full.content ?? '').indexOf(finding.earlier_quote);
					if (offset >= 0) editorRef.current?.focusRange(offset, offset + finding.earlier_quote.length);
				} catch (cause) {
					setError(cause instanceof Error ? cause.message : 'That earlier passage could not be opened.');
				}
			}, 80);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'That earlier chapter could not be opened.');
		}
	}

	if (loading) return <main className="quiet-loading"><span className="loading-mark" /><p>Opening your writing desk…</p></main>;
	if (!story) return <main className="quiet-loading"><p>{error || 'This story is not available.'}</p><button className="text-button" onClick={() => router.push("/dashboard")}>Back to stories</button></main>;

	const savedScanReady = lastScan !== null && activeChapter !== null && lastScan.chapterId === activeChapter.id && lastScan.revision === activeChapter.revision;
	const threads = entries.filter((entry) => entry.category === 'plot_thread' && entry.status !== 'dismissed');
	const chapterMentions = activeChapter ? entries.filter((entry) => entry.source_chapter_id === activeChapter.id && entry.category !== 'plot_thread') : [];
	const openThreads = threads.filter((item) => item.thread_state === 'open').length;

	// A selection in the manuscript is enough to start an entry, a fact, or a thread.
	const openCapture = (mode: CaptureMode) => {
		if (!activeChapter || !selection) return;
		setCapture({ mode, text: selection.text.slice(0, 1000), line: selection.line });
	};

	return (
		<main className={'studio-shell' + (focusMode ? ' focus-mode' : '')}>
			<aside className="chapter-rail">
				<div className="rail-brand-row"><button className="wordmark" onClick={() => void go("/dashboard")}><span className="wordmark-icon">s</span>stillroom</button><button className="back-link" onClick={() => void go("/dashboard")} aria-label="Back to stories">←</button></div>
				<div className="book-label">YOUR STORY</div><div className="rail-story-title" title={story.title}>{story.title}</div>
				<div className="chapter-list-heading"><span>CHAPTERS</span><span>{chapters.length}</span></div>
				<ChapterRail
					chapters={chapters}
					arcs={arcs}
					activeId={activeId}
					onSelect={(chapter) => void selectChapter(chapter)}
					onMove={(chapterId, delta) => void reorderChapter(chapterId, delta)}
					onDelete={(chapter) => void deleteChapter(chapter)}
					onAssign={(chapterId, arcId) => void assignArc(chapterId, arcId)}
					onCreateArc={createArc}
				/>
				<button className="new-chapter-button" onClick={() => void addChapter()}>＋ <span>New chapter</span></button>
				{activeChapter && otherStories.length > 0 && <label className="move-chapter-control"><span>Move active chapter</span><select defaultValue="" onChange={(event) => { if (event.target.value) void moveActiveChapter(event.target.value); event.target.value = ''; }}><option value="">Choose a story…</option>{otherStories.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>}
				<label className="import-button">↥ <span>Import .txt or .md</span><input type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" onChange={(event) => void importManuscript(event)} /></label>
				<button className="import-button" onClick={() => void exportManuscript()}>↓ <span>Export manuscript</span></button>
				<div className="rail-footer"><span className="quiet-dot" /> Your words stay yours</div>
			</aside>

			<section className="writing-column">
				<header className="studio-topbar">
					<div className="studio-breadcrumb"><button className="text-button" onClick={() => void go("/dashboard")}>Stories</button><span>/</span><span>{story.title}</span></div>
					<div className="studio-actions"><button className="studio-section-link" onClick={() => { setPane('find'); setPaneOpen(true); }}>Find in story</button><button className="studio-section-link" onClick={() => void go('/editing')}>Editing files</button>{(() => {
						const status = saveStatus(saveState);
						const isError = status.tone === 'error';
						return (
							<span className={'save-state save-' + status.tone} role={isError ? 'alert' : 'status'} aria-live={isError ? 'assertive' : 'polite'}>
								{status.label}
								{(saveState.status === 'error' || saveState.status === 'conflict') && <button className="text-button" onClick={() => void flushSaves()}>Retry</button>}
							</span>
						);
					})()}<button className="quiet-button focus-toggle" onClick={() => setFocusMode((value) => !value)}>{focusMode ? 'Show notes' : 'Quiet view'}</button></div>
				</header>
				{error && <div className="studio-notice error-notice" role="alert">{error}</div>}
				{notice && <div className="studio-notice" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}>×</button></div>}
				{!activeChapter ? <div className="first-chapter"><div className="first-chapter-flower">✳</div><div className="eyebrow">A BLANK PAGE, ON PURPOSE</div><h1>Begin wherever you are.</h1><p>No prompts, no generated prose. Just your manuscript and a careful memory for its details.</p><button className="button button-primary" onClick={() => void addChapter()}>Start the first chapter</button></div> : <>
					<div className="editor-toolbar"><div className="chapter-kicker">CHAPTER {String(activeChapter.chapter_number).padStart(2, '0')}</div><div className="editor-toolbar-right"><span>{editorPreferences.wordGoal > 0 ? `${words.toLocaleString()} / ${editorPreferences.wordGoal.toLocaleString()} words` : `${words.toLocaleString()} words`}</span><EditorPreferencesMenu preferences={editorPreferences} onChange={updateEditorPreferences} /><button className="text-button history-trigger" onClick={() => void openChapterHistory()}>Version history</button><span className={'index-indicator index-' + activeChapter.index_status}>{activeChapter.index_status === 'indexed' ? 'Memory ready' : activeChapter.index_status === 'failed' ? 'Memory paused' : 'Updating memory'}</span></div></div>
					{activeChapter.index_status === 'failed' && <div className="index-error">Story memory could not update. Check that the local Ollama embedding service is running. <button className="text-button" onClick={() => void retryIndex()}>Try again</button></div>}
					<div className="editor-page">
						<input className="chapter-title-input" aria-label="Chapter title" value={draftTitle} onChange={(event) => { draftEditVersionRef.current += 1; draftRef.current = { ...draftRef.current, chapterId: activeChapter.id, title: event.target.value }; setHasUnsavedChanges(true); setDraftTitle(event.target.value); }} onBlur={() => void persistChapter(activeChapter.id, draftTitle, draftContent)} placeholder="Chapter title" maxLength={200} />
						<div className="editor-rule" />
						<ManuscriptEditor
							ref={editorRef}
							chapterId={activeChapter.id}
							value={draftContent}
							onChange={(content) => {
								draftEditVersionRef.current += 1;
								draftRef.current = { ...draftRef.current, chapterId: activeChapter.id, content };
								setHasUnsavedChanges(true);
								setDraftContent(content);
							}}
							onSelectionChange={setSelection}
							onBlur={() => void persistChapter(activeChapter.id, draftTitle, editorRef.current?.getValue() ?? draftContent)}
							preferences={editorPreferences}
							entities={wikiEntities}
							findings={currentFindings}
							onOpenEntity={openEntity}
							onFindingAction={handleFindingAction}
							onOpenEvidence={(finding) => void openFindingEvidence(finding)}
							ariaLabel="Chapter manuscript"
						/>
						{activeChapter.index_status === 'indexing' && <div className="indexing-note"><span className="tiny-spinner" /> Story memory is quietly catching up.</div>}
						{selection && (
							<div className="selection-actions" role="toolbar" aria-label="Capture the selected passage">
								<span className="selection-label">Line {selection.line} selected</span>
								<button className="text-button" onClick={() => openCapture('entity')}>Add to wiki</button>
								<button className="text-button" onClick={() => openCapture('fact')}>Add fact</button>
								<button className="text-button" onClick={() => openCapture('thread')}>Add thread</button>
								<button className="text-button subtle" onClick={() => setSelection(null)}>Dismiss</button>
							</div>
						)}
					</div>
					<footer className="editor-footer"><span>Autosaves after a short pause · Ctrl/Cmd+S saves now</span><span>Stillroom does not generate story text.</span></footer>
				</>}
			</section>

			<CommandPalette
				storyId={storyId}
				chapters={chapters}
				onChapter={(chapterId) => {
					const target = chapters.find((chapter) => chapter.id === chapterId);
					if (target) void selectChapter(target);
				}}
				onQuietView={() => setFocusMode((value) => !value)}
				extra={[{ label: 'Ask your story', hint: 'Cited answer', run: () => { setPane('find'); setPaneOpen(true); setAskFocus((value) => value + 1); } }]}
			/>

			{!focusMode && !paneOpen && (
				<button className="pane-reopen" onClick={() => setPaneOpen(true)} title="Show the desk (Ctrl/Cmd + .)">‹ Desk</button>
			)}
			{!focusMode && paneOpen && <aside className="insights-pane" style={{ width: paneWidth }}>
				<button
					className="pane-resize"
					aria-label="Resize the desk"
					title="Drag to resize"
					onPointerDown={(event) => {
						const startX = event.clientX;
						const startWidth = paneWidth;
						const move = (moveEvent: PointerEvent) => setPaneWidth(Math.min(Math.max(startWidth - (moveEvent.clientX - startX), 320), 720));
						const up = () => {
							window.removeEventListener('pointermove', move);
							window.removeEventListener('pointerup', up);
							setPaneWidth((width) => {
								window.localStorage.setItem('stillroom:pane-width', String(width));
								return width;
							});
						};
						window.addEventListener('pointermove', move);
						window.addEventListener('pointerup', up);
					}}
				/>
				<div className="insights-heading"><div><div className="eyebrow">THE STORY, REMEMBERED</div><h2>Chapter desk</h2></div><span className="provider-status">{story.external_analysis_enabled ? 'AI checks on' : 'AI checks off'}</span></div>
				<div className="pane-tabs" role="tablist" aria-label="Chapter desk pages"><button role="tab" aria-selected={pane === 'notes'} className={pane === 'notes' ? 'active' : ''} onClick={() => setPane('notes')}>Notes</button><button role="tab" aria-selected={pane === 'findings'} className={pane === 'findings' ? 'active' : ''} onClick={() => setPane('findings')}>Findings <span>{currentFindings.length}</span></button><button role="tab" aria-selected={pane === 'mentions'} className={pane === 'mentions' ? 'active' : ''} onClick={() => setPane('mentions')}>Mentions <span>{chapterMentions.length}</span></button><button role="tab" aria-selected={pane === 'find'} className={pane === 'find' ? 'active' : ''} onClick={() => setPane('find')}>Find</button><button className="pane-collapse" aria-label="Collapse the desk" title="Collapse (Ctrl/Cmd + .)" onClick={() => setPaneOpen(false)}>›</button></div>
				<div className="pane-content">
					{pane === 'notes' && <section className="notes-pane">
						<div className="pane-section-title"><strong>This chapter</strong><span>{activeChapter ? `Chapter ${activeChapter.chapter_number}` : 'No chapter open'}</span></div>
						<p className="pane-hint">{activeChapter ? activeChapter.title : 'Open a chapter to see what the story already knows about it.'}</p>
						<dl className="notes-stats"><div><dt>Mentioned here</dt><dd>{chapterMentions.length}</dd></div><div><dt>Open threads</dt><dd>{openThreads}</dd></div></dl>
						{chapterMentions.length > 0 && <ul className="notes-mentions">{chapterMentions.slice(0, 12).map((entry) => <li key={entry.id}><button className="link-button" onClick={() => void go(`/stories/${storyId}/wiki/${entry.id}`)}>{entry.name}</button><span>{CATEGORY_LABEL[entry.category]}</span></li>)}</ul>}
						<div className="pane-links"><Link href={`/stories/${storyId}/wiki/review`}>Review inbox</Link><Link href={`/stories/${storyId}/wiki`}>Open the wiki</Link><Link href="/settings">AI settings</Link></div>
						<section className="notes-threads">
							<div className="pane-section-title"><strong>Open threads</strong><span>{openThreads}</span></div>
							{threads.length ? threads.map((entry) => <article className={'thread-card' + (entry.thread_state === 'resolved' ? ' resolved' : '')} key={entry.id}><div className="thread-status">{entry.thread_state === 'resolved' ? 'Resolved' : 'Still open'}</div><h3>{entry.name}</h3><p>{entry.description}</p><div className="bible-entry-actions"><button className="text-button" onClick={() => void setThread(entry, entry.thread_state === 'resolved' ? 'open' : 'resolved')}>{entry.thread_state === 'resolved' ? 'Reopen thread' : 'Mark resolved'}</button>{entry.source_chapter_id && <button className="text-button subtle" onClick={() => void openBibleSource(entry)}>Open source</button>}</div></article>) : <div className="pane-empty">Unresolved setups and questions will appear here when they are noticed in your chapters.</div>}
						</section>
						<div className="pane-section-title"><strong>Checks for this story</strong><span>{story.external_analysis_enabled ? 'Enabled' : 'Paused'}</span></div>
						<label className="story-analysis-toggle">
							<span><strong>Allow external AI analysis</strong><small>Chapter text and relevant earlier passages go to your selected API host.</small></span>
							<input type="checkbox" checked={story.external_analysis_enabled} onChange={(event) => void changeStorySetting({ external_analysis_enabled: event.target.checked })} />
						</label>
						<label className="ai-field">
							<span>Automatic check interval</span>
							<select value={story.scan_interval_words} disabled={!story.external_analysis_enabled} onChange={(event) => void changeStorySetting({ scan_interval_words: Number(event.target.value) })}>
								<option value={0}>Off · check manually</option>
								<option value={500}>Every 500 new words</option>
								<option value={1000}>Every 1,000 new words</option>
								<option value={1500}>Every 1,500 new words</option>
								<option value={3000}>Every 3,000 new words</option>
							</select>
							<small>Automatic checks are optional. You can also check a draft manually.</small>
						</label>
						<div className="ai-privacy-note"><strong>Privacy</strong><p>External analysis is limited to this story. Local indexing stays on Ollama.</p></div>
						<section className="ai-usage-panel">
							<div className="pane-section-title"><strong>AI usage this month</strong><span>{aiUsage ? `${aiUsage.calls} ${aiUsage.calls === 1 ? 'call' : 'calls'}` : 'No calls yet'}</span></div>
							<dl className="notes-stats">
								<div><dt>Spent</dt><dd>{aiUsage ? `$${aiUsage.spent_usd.toFixed(2)}` : '$0.00'}</dd></div>
								<div><dt>Tokens</dt><dd>{aiUsage ? (aiUsage.input_tokens + aiUsage.output_tokens).toLocaleString() : '0'}</dd></div>
							</dl>
							<label className="ai-field">
								<span>Monthly cloud budget (USD)</span>
								<input key={story.monthly_ai_budget} type="number" min={0} step={5} defaultValue={story.monthly_ai_budget} onBlur={(event) => { const value = Math.max(0, Number(event.target.value) || 0); if (value !== story.monthly_ai_budget) void changeStorySetting({ monthly_ai_budget: value }); }} />
								<small>Zero keeps this story local-only. Cloud scans are refused before they spend above the budget.</small>
							</label>
							{aiUsage && aiUsage.by_purpose.length > 0 && <ul className="notes-mentions">{aiUsage.by_purpose.slice(0, 4).map((entry) => <li key={`${entry.purpose}-${entry.model}`}><span>{entry.purpose}</span><span>{entry.calls} · ${entry.cost_usd.toFixed(3)}</span></li>)}</ul>}
						</section>
						<section className="bible-scan-panel">
							<div className="pane-section-title"><strong>Read for details</strong><span>Finds proposals</span></div>
							<p className="pane-hint">Choose a chapter range. Anything found becomes a proposal in the review inbox.</p>
							<div className="bible-scan-range">
								<label><span>From</span><select value={bibleScanStart} onChange={(event) => setBibleScanStart(Number(event.target.value))}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.chapter_number}>{chapter.chapter_number}. {chapter.title}</option>)}</select></label>
								<label><span>Through</span><select value={bibleScanEnd} onChange={(event) => setBibleScanEnd(Number(event.target.value))}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.chapter_number}>{chapter.chapter_number}. {chapter.title}</option>)}</select></label>
							</div>
							<button className="button button-bible-scan" onClick={() => void scanBibleRange()} disabled={!chapters.length || hasUnsavedChanges || scanningBible || bibleScanPending.length > 0 || bibleScanStart > bibleScanEnd}>{scanningBible ? 'Queueing scan…' : 'Read range'}</button>
							<label className="bible-scan-force"><input type="checkbox" checked={bibleScanForce} onChange={(event) => setBibleScanForce(event.target.checked)} /><span>Read unchanged chapters again</span></label>
							{bibleScanMessage && <p className={`bible-scan-message${bibleScanFailed ? ' is-error' : ''}`} role="status">{bibleScanMessage}</p>}
						</section>
					</section>}
					{pane === 'find' && <StorySearch storyId={storyId} chapters={chapters} arcs={arcs} focusAsk={askFocus} onOpen={(chapterId, line) => void openSearchHit(chapterId, line)} />}
					{pane === 'mentions' && <NameCandidatesPanel
						storyId={storyId}
						chapter={activeChapter ? { id: activeChapter.id, chapter_number: activeChapter.chapter_number, title: activeChapter.title } : null}
						onOpenEntity={(entityId) => void go(`/stories/${storyId}/wiki/${entityId}`)}
					/>}
					{pane === 'findings' && <section>
						<div className="pane-section-title continuity-title">
							<strong>Continuity findings <span className="finding-count">{currentFindings.filter((item) => item.review_status === 'open').length}</span></strong>
							<select className="finding-filter" aria-label="Choose chapter findings" value={findingsTargetChapterId || activeId} onChange={(event) => void changeFindingChapter(event.target.value)}><option value="" disabled>Select chapter</option>{chapters.map((item) => <option key={item.id} value={item.id}>Ch. {item.chapter_number}</option>)}</select>
							<select className="finding-filter" aria-label="Filter continuity findings" value={findingFilter} onChange={(event) => setFindingFilter(event.target.value as typeof findingFilter)}><option value="open">Open</option><option value="resolved">Resolved</option><option value="dismissed">Dismissed</option><option value="all">All</option></select>
							<button className="button button-check" disabled={!activeChapter || findingsTargetChapterId !== activeId || !story.external_analysis_enabled || !earlierChaptersReady || activeChapter.index_status !== 'indexed' || checking || checkRetryCountdown > 0} onClick={() => void runCheck()}>
								{checking ? <><span className="tiny-spinner" /> {scanProgress?.scenes_total ? `Checking ${scanProgress.scenes_done ?? 0}/${scanProgress.scenes_total}…` : 'Checking…'}</> : checkRetryCountdown > 0 ? `Retry in ${checkRetryCountdown}s` : 'Check draft'}
							</button>
							{checking && activeChapter && <button className="text-button" onClick={() => void cancelScan(activeChapter.id)}>Cancel</button>}
						</div>
						<p className="pane-hint">{findingsTargetChapterId !== activeId ? 'You are viewing saved findings for another chapter. Select the open chapter to run a new check.' : !story.external_analysis_enabled ? 'Enable AI checks in AI settings to review this draft.' : !earlierChapters.length ? 'Add an earlier chapter to compare against.' : !earlierChaptersReady ? 'Waiting for earlier chapters to finish indexing.' : activeChapter?.index_status !== 'indexed' ? 'This chapter is still being indexed.' : 'Potential conflicts pair a line in this draft with evidence from earlier chapters only.'}</p>
						{savedScanReady && <div className="reuse-hint"><span>These findings are already stored for this saved draft. Check draft reuses them at no provider cost.</span><button className="text-button" title="Send this draft to your provider again" disabled={findingsTargetChapterId !== activeId || !story.external_analysis_enabled || !earlierChaptersReady || activeChapter.index_status !== 'indexed' || checking || checkRetryCountdown > 0} onClick={() => void runCheck(false, true)}>Run again</button></div>}
						{visibleFindings.length ? visibleFindings.map((finding) => <article className={'finding-card status-' + finding.review_status} key={finding.id}><div className="finding-card-top"><span>LINE {finding.draft_line} · {finding.review_status.toUpperCase()}</span><span>{finding.confidence}% confidence</span></div><p className="finding-explanation">{finding.explanation}</p><div className="evidence-pair"><div className="draft-evidence"><small>THIS DRAFT · LINE {finding.draft_line}</small><button onClick={() => void openFindingLine(finding)}>“{finding.draft_quote}”</button></div><div className="earlier-evidence"><small>EARLIER · CHAPTER {finding.earlier_chapter_number} · {finding.earlier_chapter_title}</small><blockquote>“{finding.earlier_quote}”</blockquote></div></div><div className="finding-review-actions">{finding.review_status !== 'resolved' && <button onClick={() => void reviewFinding(finding, 'resolved')}>Resolve</button>}{finding.review_status !== 'open' && <button onClick={() => void reviewFinding(finding, 'open')}>Reopen</button>}{finding.review_status !== 'dismissed' && <button onClick={() => void reviewFinding(finding, 'dismissed')}>Dismiss</button>}</div>{finding.review_status === 'open' && <button className="intentional-button" onClick={() => void markIntentional(finding)}>Mark as intentional</button>}</article>) : <div className="pane-empty">{currentFindings.length ? 'No findings match this filter.' : findingsChapterId === findingsTargetChapterId ? 'No conflicts to review. Run a draft check when you’re ready.' : 'Loading saved findings…'}</div>}
					</section>}
				</div>
				<div className="pane-bottom-note">Suggestions are drafts for your approval. Nothing becomes canon without you.</div>
			</aside>}
			{capture && activeChapter && (
				<CaptureDialog
					storyId={storyId}
					story={story}
					chapterId={activeChapter.id}
					chapterNumber={activeChapter.chapter_number}
					selection={capture}
					onClose={() => setCapture(null)}
					onDone={() => { setCapture(null); setSelection(null); void refreshBible(); }}
				/>
			)}
			{recovered && <div className="studio-notice" role="status">Recovered unsaved changes from this browser.<button aria-label="Dismiss message" onClick={() => setRecovered(false)}>×</button></div>}
			<ConflictDialog
				open={conflict !== null}
				localTitle={conflict?.localTitle ?? ''}
				localContent={conflict?.localContent ?? ''}
				serverTitle={conflict?.serverTitle ?? ''}
				serverContent={conflict?.serverContent ?? ''}
				serverRevision={conflict?.serverRevision ?? 0}
				onKeepMine={() => void keepMyVersion()}
				onReloadServer={() => void reloadSavedVersion()}
				onCopyChanges={copyChangesForMerge}
			/>
			{historyOpen && <div className="history-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setHistoryOpen(false); }}>
				<section className="history-dialog" role="dialog" aria-modal="true" aria-label="Chapter version history">
					<header>
						<div><div className="eyebrow">DRAFT SAFETY</div><h2>Version history</h2><p>Pin a checkpoint before a big rewrite. Select two versions to compare them.</p></div>
						<button className="quiet-button" onClick={() => setHistoryOpen(false)}>Close</button>
					</header>
					<div className="history-actions">
						<button className="button button-approve" disabled={!activeChapter} onClick={() => void saveCheckpoint()}>Save checkpoint</button>
						{historySelection.length === 2 && <button className="quiet-button" onClick={() => void compareVersions(historySelection[0], historySelection[1])}>Compare selected</button>}
					</div>
					{historyLoading ? <div className="pane-empty">Loading saved versions…</div> : chapterHistory.length ? (
						<div className="history-list">
							{chapterHistory.map((revision) => (
								<article key={revision.revision_number} className={historySelection.includes(revision.revision_number) ? 'selected' : ''}>
									<div>
										<strong>Version {revision.revision_number} <span className={'history-kind kind-' + revision.kind}>{revision.kind}</span></strong>
										<span>{revision.title} · {revision.word_count.toLocaleString()} words</span>
										<time>{new Date(revision.created_at).toLocaleString()}</time>
									</div>
									<div className="history-row-actions">
										<label className="history-pick">
											<input
												type="checkbox"
												checked={historySelection.includes(revision.revision_number)}
												onChange={() => setHistorySelection((current) => current.includes(revision.revision_number) ? current.filter((value) => value !== revision.revision_number) : [...current, revision.revision_number].slice(-2))}
												aria-label={`Select version ${revision.revision_number} for comparison`}
											/>
											<span>Compare</span>
										</label>
										<button className="button button-approve" onClick={() => void restoreChapterHistory(revision)}>Restore</button>
									</div>
								</article>
							))}
						</div>
					) : <div className="pane-empty">Older versions appear here after the chapter is edited.</div>}
					{historyDiff && <section className="history-diff" aria-label="Version differences">
						<header><strong>Versions {historyDiff.older.revision_number} → {historyDiff.newer.revision_number}</strong><button className="text-button" onClick={() => setHistoryDiff(null)}>Hide</button></header>
						{historyDiff.hunks.length ? historyDiff.hunks.map((hunk, index) => (
							<div className="diff-hunk" key={index}>
								<div className="diff-hunk-head">@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@</div>
								{hunk.lines.map((line, lineIndex) => {
									const kind = line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : 'same';
									return <div key={lineIndex} className={'diff-line diff-' + kind}><span className="diff-gutter">{line.slice(0, 1)}</span><span className="diff-text">{line.slice(1) || ' '}</span></div>;
								})}
							</div>
						)) : <p className="pane-empty">No line changes between those versions.</p>}
					</section>}
				</section>
			</div>}
		</main>
	);
}
