"use client";

import { markdown } from '@codemirror/lang-markdown';
import { defaultKeymap, history, historyField, historyKeymap, indentWithTab } from '@codemirror/commands';
import { bracketMatching, defaultHighlightStyle, indentOnInput, syntaxHighlighting } from '@codemirror/language';
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search';
import { Compartment, EditorState, RangeSetBuilder, type Extension } from '@codemirror/state';
import {
	EditorView,
	crosshairCursor,
	drawSelection,
	dropCursor,
	highlightActiveLine,
	highlightActiveLineGutter,
	highlightSpecialChars,
	keymap,
	lineNumbers,
	placeholder,
	rectangularSelection,
	Decoration,
	ViewPlugin,
	type DecorationSet,
	type ViewUpdate,
} from '@codemirror/view';
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';

import type { ContinuityFinding, WikiEntity } from '@/lib/api';
import { getEditorState, putEditorState } from '@/lib/editor-state-store';
import type { EditorPreferences } from '@/lib/editor-preferences';
import { buildEntityMatcher, type EntityMatcher } from '@/lib/entity-matcher';
import { annotationField, buildAnnotations, createFindingGutter, findingRange, setAnnotations } from '@/lib/manuscript-decorations';
import type { StyleIssue } from '@/lib/style-analysis';

export type ManuscriptFormat = 'bold' | 'italic' | 'underline' | 'strike' | 'highlight' | 'h2' | 'quote' | 'bullet' | 'color' | 'clear';

export interface ManuscriptEditorHandle {
	focus: () => void;
	applyFormat: (command: ManuscriptFormat, color?: string) => void;
	focusRange: (from: number, to: number) => void;
	focusLine: (line: number) => void;
	getSelection: () => { text: string; from: number; to: number; line: number } | null;
	getValue: () => string;
	flush: () => void;
}

export type FindingAction = 'resolve' | 'dismiss' | 'intentional';

interface ManuscriptEditorProps {
	chapterId: string;
	value: string;
	onChange: (value: string) => void;
	onSelectionChange?: (selection: { text: string; line: number } | null) => void;
	preferences: EditorPreferences;
	entities?: WikiEntity[];
	findings?: ContinuityFinding[];
	styleIssues?: StyleIssue[];
	onOpenEntity?: (entityId: string) => void;
	onStyleIssue?: (issue: StyleIssue) => void;
	onFindingAction?: (finding: ContinuityFinding, action: FindingAction) => void;
	onOpenEvidence?: (finding: ContinuityFinding) => void;
	ariaLabel?: string;
	autoFocus?: boolean;
	onBlur?: () => void;
}

type EditorPopover =
	| { kind: 'entity'; entityId: string; x: number; y: number }
	| { kind: 'finding'; findingId: string; x: number; y: number };

const EMIT_DEBOUNCE_MS = 180;
const PERSIST_DEBOUNCE_MS = 500;
const ANNOTATION_DEBOUNCE_MS = 300;

function themeFor(preferences: EditorPreferences): Extension {
	return EditorView.theme({
		'&': { fontSize: `${preferences.fontSize}px`, lineHeight: String(preferences.lineHeight) },
		'.cm-content': {
			fontFamily: preferences.fontFamily === 'serif' ? 'var(--font-serif)' : 'var(--font-sans)',
			maxWidth: `${preferences.measure}px`,
		},
	});
}

type InlineFormat = { from: number; to: number; contentFrom: number; contentTo: number; className: string; color?: string };

function collectInlineFormats(view: EditorView): DecorationSet {
	const candidates: InlineFormat[] = [];
	const seen = new Set<string>();
	for (const visible of view.visibleRanges) {
		const start = view.state.doc.lineAt(visible.from).from;
		const end = view.state.doc.lineAt(visible.to).to;
		const text = view.state.doc.sliceString(start, end);
		const patterns: Array<{ regex: RegExp; open: number; close: number; className: string }> = [
			{ regex: /\*\*([^*]+?)\*\*/g, open: 2, close: 2, className: 'cm-format-bold' },
			{ regex: /~~([^~]+?)~~/g, open: 2, close: 2, className: 'cm-format-strike' },
			{ regex: /==([^=]+?)==/g, open: 2, close: 2, className: 'cm-format-highlight' },
			{ regex: /<u>([^<]+?)<\/u>/g, open: 3, close: 4, className: 'cm-format-underline' },
			{ regex: /\*([^*]+?)\*/g, open: 1, close: 1, className: 'cm-format-italic' },
		];
		for (const pattern of patterns) {
			for (const match of text.matchAll(pattern.regex)) {
				if (match.index === undefined) continue;
				const from = start + match.index;
				const key = `${from}:${match[0].length}:${pattern.className}`;
				if (seen.has(key)) continue;
				seen.add(key);
				candidates.push({ from, to: from + match[0].length, contentFrom: from + pattern.open, contentTo: from + match[0].length - pattern.close, className: pattern.className });
			}
		}
		for (const match of text.matchAll(/<span style="color:(#[0-9a-fA-F]{3,8})">([^<]+?)<\/span>/g)) {
			if (match.index === undefined) continue;
			const from = start + match.index;
			const key = `${from}:${match[0].length}:color`;
			if (seen.has(key)) continue;
			seen.add(key);
			const open = match[0].indexOf('>') + 1;
			candidates.push({ from, to: from + match[0].length, contentFrom: from + open, contentTo: from + match[0].length - 7, className: 'cm-format-color', color: match[1] });
		}
	}
	candidates.sort((a, b) => a.from - b.from || a.to - b.to);
	const builder = new RangeSetBuilder<Decoration>();
	let lastEnd = -1;
	for (const candidate of candidates) {
		if (candidate.from < lastEnd || candidate.contentTo <= candidate.contentFrom) continue;
		builder.add(candidate.from, candidate.contentFrom, Decoration.replace({}));
		builder.add(candidate.contentFrom, candidate.contentTo, Decoration.mark({ class: candidate.className, attributes: candidate.color ? { style: `color:${candidate.color}` } : undefined }));
		builder.add(candidate.contentTo, candidate.to, Decoration.replace({}));
		lastEnd = candidate.to;
	}
	return builder.finish();
}

const inlineFormatting = ViewPlugin.fromClass(class {
	decorations: DecorationSet;
	constructor(view: EditorView) { this.decorations = collectInlineFormats(view); }
	update(update: ViewUpdate) { if (update.docChanged || update.viewportChanged) this.decorations = collectInlineFormats(update.view); }
}, { decorations: (value) => value.decorations });

function clamp(value: number, minimum: number, maximum: number): number {
	return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

function markFromEvent(event: Event): HTMLElement | null {
	const target = event.target as HTMLElement | null;
	if (!target) return null;
	// A finding can overlap an entity mention. The finding owns the click so
	// its review actions are always reachable.
	return target.closest<HTMLElement>('[data-finding-id]') ?? target.closest<HTMLElement>('[data-entity-id]');
}

/**
 * CodeMirror owns the document while it is mounted. The parent receives a
 * debounced copy so the studio does not rerender on every keystroke, and the
 * full editor state (including undo history) is checkpointed to IndexedDB.
 * Entity and finding decorations are a separate state field, so a recompute
 * never rewrites a single character of the manuscript.
 */
export const ManuscriptEditor = forwardRef<ManuscriptEditorHandle, ManuscriptEditorProps>(
	function ManuscriptEditor({
		chapterId, value, onChange, onSelectionChange, preferences, entities = [], findings = [], styleIssues = [], onOpenEntity, onStyleIssue, onFindingAction, onOpenEvidence, ariaLabel, autoFocus, onBlur,
	}, ref) {
		const hostRef = useRef<HTMLDivElement>(null);
		const viewRef = useRef<EditorView | null>(null);
		const onChangeRef = useRef(onChange);
		const onSelectionRef = useRef(onSelectionChange);
		const onBlurRef = useRef(onBlur);
		const onOpenEntityRef = useRef(onOpenEntity);
		const onStyleIssueRef = useRef(onStyleIssue);
		const onFindingActionRef = useRef(onFindingAction);
		const onOpenEvidenceRef = useRef(onOpenEvidence);
		const entitiesRef = useRef<WikiEntity[]>(entities);
		const findingsRef = useRef<ContinuityFinding[]>(findings);
		const styleIssuesRef = useRef<StyleIssue[]>(styleIssues);
		const pendingFocusRef = useRef<{ line?: number; from?: number; to?: number } | null>(null);
		const preferencesRef = useRef(preferences);
		const valueRef = useRef(value);
		const autoFocusRef = useRef(autoFocus);
		const ariaLabelRef = useRef(ariaLabel);
		const lastEmittedRef = useRef(value);
		const emitTimerRef = useRef<number | null>(null);
		const persistTimerRef = useRef<number | null>(null);
		const annotationTimerRef = useRef<number | null>(null);
		const closeTimerRef = useRef<number | null>(null);
		const chapterRef = useRef(chapterId);
		const themeCompartment = useRef(new Compartment());
		const matcherRef = useRef<EntityMatcher | null>(null);
		const matcherEntitiesRef = useRef<WikiEntity[] | null>(null);
		const popoverRef = useRef<HTMLDivElement>(null);
		const [popover, setPopover] = useState<EditorPopover | null>(null);
		const [findingIndex, setFindingIndex] = useState(0);

		onChangeRef.current = onChange;
		onSelectionRef.current = onSelectionChange;
		onBlurRef.current = onBlur;
		onOpenEntityRef.current = onOpenEntity;
		onStyleIssueRef.current = onStyleIssue;
		onFindingActionRef.current = onFindingAction;
		onOpenEvidenceRef.current = onOpenEvidence;
		entitiesRef.current = entities;
		findingsRef.current = findings;
		styleIssuesRef.current = styleIssues;
		preferencesRef.current = preferences;
		valueRef.current = value;
		autoFocusRef.current = autoFocus;
		ariaLabelRef.current = ariaLabel;
		chapterRef.current = chapterId;

		const flush = () => {
			if (emitTimerRef.current !== null) {
				window.clearTimeout(emitTimerRef.current);
				emitTimerRef.current = null;
			}
			const view = viewRef.current;
			if (!view) return;
			const next = view.state.doc.toString();
			if (next === lastEmittedRef.current) return;
			lastEmittedRef.current = next;
			onChangeRef.current(next);
		};

		const persist = (chapter = chapterRef.current) => {
			const view = viewRef.current;
			if (!view) return;
			const doc = view.state.doc.toString();
			try {
				const json = view.state.toJSON({ history: historyField });
				void putEditorState({ chapterId: chapter, doc, json, updatedAt: Date.now() }).catch(() => undefined);
			} catch {
				// A state that cannot be serialized must never block typing.
			}
		};

		const emitSelection = (state: EditorState) => {
			const range = state.selection.main;
			const text = state.sliceDoc(range.from, range.to);
			onSelectionRef.current?.(text.trim() ? { text: text.trim(), line: state.doc.lineAt(range.from).number } : null);
		};

		const positionFor = (element: HTMLElement | null, fallback = 24): { x: number; y: number } => {
			const host = hostRef.current;
			if (!host || !element) return { x: fallback, y: fallback };
			const hostRect = host.getBoundingClientRect();
			const rect = element.getBoundingClientRect();
			const x = clamp(rect.left - hostRect.left, 8, hostRect.width - 330);
			const below = rect.bottom - hostRect.top + 7;
			const y = below > hostRect.height - 230 ? Math.max(8, rect.top - hostRect.top - 205) : below;
			return { x, y };
		};

		const cancelClose = () => {
			if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
			closeTimerRef.current = null;
		};

		const closeSoon = () => {
			cancelClose();
			closeTimerRef.current = window.setTimeout(() => setPopover(null), 220);
		};

		const showEntity = (entityId: string, element: HTMLElement | null) => {
			cancelClose();
			const position = positionFor(element);
			setPopover((current) => current?.kind === 'entity' && current.entityId === entityId ? current : { kind: 'entity', entityId, ...position });
		};

		const showFinding = (findingId: string, element: HTMLElement | null) => {
			const finding = findingsRef.current.find((item) => item.id === findingId);
			if (!finding) return;
			cancelClose();
			const view = viewRef.current;
			const position = element ? positionFor(element) : { x: 42, y: 42 };
			if (!element && view) {
				const range = findingRange(view.state, finding);
				const coords = view.coordsAtPos(range.from);
				if (coords) {
					const hostRect = hostRef.current?.getBoundingClientRect();
					if (hostRect) {
						position.x = clamp(coords.left - hostRect.left, 8, hostRect.width - 330);
						position.y = clamp(coords.bottom - hostRect.top + 7, 8, Math.max(8, hostRect.height - 230));
					}
				}
			}
			setPopover((current) => current?.kind === 'finding' && current.findingId === findingId ? current : { kind: 'finding', findingId, ...position });
		};

		const recomputeAnnotations = () => {
			const view = viewRef.current;
			if (!view) return;
			const currentEntities = entitiesRef.current;
			if (matcherEntitiesRef.current !== currentEntities || !matcherRef.current) {
				matcherRef.current = buildEntityMatcher(currentEntities);
				matcherEntitiesRef.current = currentEntities;
			}
			const payload = buildAnnotations(view.state, matcherRef.current, currentEntities, findingsRef.current, styleIssuesRef.current);
			view.dispatch({ effects: setAnnotations.of(payload) });
		};

		const scheduleAnnotations = () => {
			if (annotationTimerRef.current !== null) window.clearTimeout(annotationTimerRef.current);
			annotationTimerRef.current = window.setTimeout(recomputeAnnotations, ANNOTATION_DEBOUNCE_MS);
		};

		const focusFindingAt = (index: number) => {
			const view = viewRef.current;
			const list = findingsRef.current;
			if (!view || list.length === 0) return;
			const safe = ((index % list.length) + list.length) % list.length;
			setFindingIndex(safe);
			const range = findingRange(view.state, list[safe]);
			view.dispatch({ selection: { anchor: range.from, head: range.to }, effects: EditorView.scrollIntoView(range.from, { y: 'center' }) });
			view.focus();
		};

		useEffect(() => {
			const host = hostRef.current;
			if (!host) return;
			let disposed = false;

			const extensions: Extension[] = [
				lineNumbers(),
				highlightActiveLineGutter(),
				highlightSpecialChars(),
				history(),
				drawSelection(),
				dropCursor(),
				rectangularSelection(),
				crosshairCursor(),
				highlightActiveLine(),
				bracketMatching(),
				indentOnInput(),
				highlightSelectionMatches(),
				syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
				markdown(),
				inlineFormatting,
				EditorView.lineWrapping,
				placeholder('Begin the chapter…'),
				keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap, indentWithTab]),
				EditorView.contentAttributes.of({
					'aria-label': ariaLabelRef.current ?? 'Manuscript chapter',
					spellcheck: 'true',
					autocapitalize: 'off',
					autocorrect: 'off',
				}),
				annotationField,
				createFindingGutter((findingId) => showFinding(findingId, null)),
				EditorView.domEventHandlers({
					keydown: (event) => {
						const styleId = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-style-id]')?.dataset.styleId;
						if (styleId && (event.key === 'Enter' || event.key === ' ')) {
							const issue = styleIssuesRef.current.find((item) => item.id === styleId);
							if (issue) {
								event.preventDefault();
								onStyleIssueRef.current?.(issue);
								return true;
							}
						}
						if (event.key === 'Escape' && popoverRef.current) {
							setPopover(null);
							event.preventDefault();
							return true;
						}
						if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
							flush();
							persist();
						}
						return false;
					},
					blur: () => {
						flush();
						persist();
						onBlurRef.current?.();
						return false;
					},
					click: (event) => {
						const mark = markFromEvent(event);
						if (mark) {
							event.preventDefault();
							const findingId = mark.dataset.findingId;
							if (findingId) { showFinding(findingId, mark); return true; }
							const entityId = mark.dataset.entityId;
							if (entityId) onOpenEntityRef.current?.(entityId);
							return true;
						}
						const styleId = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-style-id]')?.dataset.styleId;
						if (styleId) {
							const issue = styleIssuesRef.current.find((item) => item.id === styleId);
							if (issue) onStyleIssueRef.current?.(issue);
							return true;
						}
						return false;
					},
					mouseover: (event) => {
						const mark = markFromEvent(event);
						if (!mark) return false;
						if (mark.dataset.findingId) showFinding(mark.dataset.findingId, mark);
						else if (mark.dataset.entityId) showEntity(mark.dataset.entityId, mark);
						return false;
					},
					mouseout: (event) => {
						const mark = markFromEvent(event);
						if (!mark) return false;
						const related = event.relatedTarget as Node | null;
						if (related && (mark.contains(related) || popoverRef.current?.contains(related))) return false;
						closeSoon();
						return false;
					},
					focusin: (event) => {
						const mark = markFromEvent(event);
						if (!mark) return false;
						if (mark.dataset.findingId) showFinding(mark.dataset.findingId, mark);
						else if (mark.dataset.entityId) showEntity(mark.dataset.entityId, mark);
						return false;
					},
					focusout: (event) => {
						const next = event.relatedTarget as Node | null;
						if (next && popoverRef.current?.contains(next)) return false;
						closeSoon();
						return false;
					},
				}),
				themeCompartment.current.of(themeFor(preferencesRef.current)),
				EditorView.updateListener.of((update: ViewUpdate) => {
					if (update.docChanged) {
						if (emitTimerRef.current !== null) window.clearTimeout(emitTimerRef.current);
						emitTimerRef.current = window.setTimeout(flush, EMIT_DEBOUNCE_MS);
						if (persistTimerRef.current !== null) window.clearTimeout(persistTimerRef.current);
						persistTimerRef.current = window.setTimeout(persist, PERSIST_DEBOUNCE_MS);
						scheduleAnnotations();
					}
					if (update.selectionSet || update.docChanged) emitSelection(update.state);
					if (preferencesRef.current.typewriter && update.selectionSet && !update.docChanged) {
						const head = update.state.selection.main.head;
						window.requestAnimationFrame(() => {
							update.view.dispatch({ effects: EditorView.scrollIntoView(head, { y: 'center' }) });
						});
					}
				}),
			];

			const create = async () => {
				let state: EditorState | null = null;
				try {
					const saved = await getEditorState(chapterId);
					if (saved && saved.doc === valueRef.current) {
						state = EditorState.fromJSON(saved.json, { extensions }, { history: historyField });
					}
				} catch {
					state = null;
				}
				if (disposed) return;
				const view = new EditorView({
					state: state ?? EditorState.create({ doc: valueRef.current, extensions }),
					parent: host,
				});
				viewRef.current = view;
				recomputeAnnotations();
				if (autoFocusRef.current) view.focus();
				const pending = pendingFocusRef.current;
				if (pending) {
					pendingFocusRef.current = null;
					const line = pending.line ?? null;
					if (line !== null) {
						const safe = Math.max(1, Math.min(line, view.state.doc.lines));
						const target = view.state.doc.line(safe);
						view.dispatch({ selection: { anchor: target.from, head: target.to }, effects: EditorView.scrollIntoView(target.from, { y: 'center' }) });
					} else {
						const from = Math.max(0, Math.min(pending.from ?? 0, view.state.doc.length));
						const to = Math.max(from, Math.min(pending.to ?? from, view.state.doc.length));
						view.dispatch({ selection: { anchor: from, head: to }, effects: EditorView.scrollIntoView(from, { y: 'center' }) });
					}
					view.focus();
				}
			};
			void create();

			const pageHide = () => persist(chapterId);
			window.addEventListener('pagehide', pageHide);

			return () => {
				window.removeEventListener('pagehide', pageHide);
				disposed = true;
				if (emitTimerRef.current !== null) window.clearTimeout(emitTimerRef.current);
				if (persistTimerRef.current !== null) window.clearTimeout(persistTimerRef.current);
				if (annotationTimerRef.current !== null) window.clearTimeout(annotationTimerRef.current);
				if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
				persist(chapterId);
				viewRef.current?.destroy();
				viewRef.current = null;
			};
			// The editor is rebuilt only when the chapter changes; callbacks are read through refs.
			// eslint-disable-next-line react-hooks/exhaustive-deps
		}, [chapterId]);

		useEffect(() => {
			const view = viewRef.current;
			if (!view) return;
			if (value === lastEmittedRef.current) return;
			if (value === view.state.doc.toString()) return;
			lastEmittedRef.current = value;
			view.dispatch({
				changes: { from: 0, to: view.state.doc.length, insert: value },
				selection: { anchor: Math.min(view.state.selection.main.head, value.length) },
			});
		}, [value]);

		useEffect(() => {
			recomputeAnnotations();
		}, [entities, findings, styleIssues]);

		useEffect(() => {
			const view = viewRef.current;
			if (!view) return;
			view.dispatch({ effects: themeCompartment.current.reconfigure(themeFor(preferences)) });
		}, [preferences]);

		useImperativeHandle(ref, () => ({
			focus: () => viewRef.current?.focus(),
			applyFormat: (command, color) => {
				const view = viewRef.current;
				if (!view) return;
				view.focus();
				const state = view.state;
				const selection = state.selection.main;
				const selected = state.sliceDoc(selection.from, selection.to);
				if (command === 'h2' || command === 'quote' || command === 'bullet') {
					const prefix = command === 'h2' ? '## ' : command === 'quote' ? '> ' : '- ';
					const start = state.doc.lineAt(selection.from).from;
					const end = state.doc.lineAt(selection.to).to;
					const block = state.sliceDoc(start, end);
					const next = block.split('\n').map((line) => (line.startsWith(prefix) ? line.slice(prefix.length) : prefix + line)).join('\n');
					view.dispatch({ changes: { from: start, to: end, insert: next }, selection: { anchor: start, head: start + next.length } });
					return;
				}
				if (command === 'clear') {
					const cleaned = selected.replace(/\*\*|__|~~|==|<\/?u>|<\/?em>|<\/?strong>/g, '').replace(/<span style="color:#[0-9a-fA-F]{3,8}">|<\/span>/g, '');
					if (!selected) return;
					view.dispatch({ changes: { from: selection.from, to: selection.to, insert: cleaned }, selection: { anchor: selection.from, head: selection.from + cleaned.length } });
					return;
				}
				const pair = command === 'bold' ? '**'
					: command === 'italic' ? '*'
					: command === 'underline' ? '<u>'
					: command === 'strike' ? '~~'
					: command === 'highlight' ? '=='
					: color ? `<span style="color:${color}">` : '';
				const closing = command === 'underline' ? '</u>' : color ? '</span>' : pair;
				if (!pair) return;
				const before = state.sliceDoc(Math.max(0, selection.from - pair.length), selection.from);
				const after = state.sliceDoc(selection.to, Math.min(state.doc.length, selection.to + closing.length));
				if (before === pair && after === closing) {
					view.dispatch({
						changes: [
							{ from: selection.from - pair.length, to: selection.from },
							{ from: selection.to, to: selection.to + closing.length },
						],
						selection: { anchor: selection.from - pair.length, head: selection.to - pair.length },
					});
					return;
				}
				const body = selected;
				view.dispatch({
					changes: { from: selection.from, to: selection.to, insert: pair + body + closing },
					selection: { anchor: selection.from + pair.length, head: selection.from + pair.length + body.length },
				});
			},
			focusRange: (from, to) => {
				const view = viewRef.current;
				if (!view) {
					pendingFocusRef.current = { from, to };
					return;
				}
				const length = view.state.doc.length;
				const anchor = Math.max(0, Math.min(from, length));
				const head = Math.max(anchor, Math.min(to, length));
				view.dispatch({
					selection: { anchor, head },
					effects: EditorView.scrollIntoView(anchor, { y: 'center' }),
				});
				view.focus();
			},
			focusLine: (line) => {
				const view = viewRef.current;
				if (!view) {
					pendingFocusRef.current = { line };
					return;
				}
				const safe = Math.max(1, Math.min(line, view.state.doc.lines));
				const target = view.state.doc.line(safe);
				const length = view.state.doc.length;
				const anchor = Math.min(target.from, length);
				const head = Math.min(target.to, length);
				view.dispatch({
					selection: { anchor, head },
					effects: EditorView.scrollIntoView(anchor, { y: 'center' }),
				});
				view.focus();
			},
			getSelection: () => {
				const view = viewRef.current;
				if (!view) return null;
				const range = view.state.selection.main;
				const text = view.state.sliceDoc(range.from, range.to);
				if (!text.trim()) return null;
				return { text: text.trim(), from: range.from, to: range.to, line: view.state.doc.lineAt(range.from).number };
			},
			getValue: () => viewRef.current?.state.doc.toString() ?? value,
			flush,
		}));

		const selectedEntity = popover?.kind === 'entity' ? entities.find((entity) => entity.id === popover.entityId) : undefined;
		const selectedFinding = popover?.kind === 'finding' ? findings.find((finding) => finding.id === popover.findingId) : undefined;
		const safeFindingIndex = findings.length ? Math.min(findingIndex, findings.length - 1) : 0;

		return (
			<div className="manuscript-frame">
				<div ref={hostRef} className={`manuscript-surface theme-${preferences.theme}${preferences.focusMode ? ' focus-mode' : ''}${preferences.typewriter ? ' typewriter-mode' : ''}`} />
				{findings.length > 0 && (
					<div className="cm-finding-nav" role="group" aria-label="Continuity findings in this chapter">
						<span aria-live="polite">Finding {safeFindingIndex + 1} of {findings.length}</span>
						<button type="button" aria-label="Previous finding" onMouseDown={(event) => event.preventDefault()} onClick={() => focusFindingAt(safeFindingIndex - 1)}>↑</button>
						<button type="button" aria-label="Next finding" onMouseDown={(event) => event.preventDefault()} onClick={() => focusFindingAt(safeFindingIndex + 1)}>↓</button>
					</div>
				)}
				{popover && (
					<div
						ref={popoverRef}
						className={`cm-canon-popover cm-canon-${popover.kind}`}
						style={{ left: popover.x, top: popover.y }}
						role="dialog"
						aria-label={popover.kind === 'entity' ? 'Entity canon card' : 'Continuity finding' }
						onMouseEnter={cancelClose}
						onMouseLeave={closeSoon}
					>
						<button type="button" className="cm-popover-close" aria-label="Close card" onClick={() => setPopover(null)}>×</button>
						{popover.kind === 'entity' && (selectedEntity ? (
							<>
								<div className="cm-popover-kicker">{selectedEntity.entity_type.replaceAll('_', ' ')}</div>
								<h3>{selectedEntity.name}</h3>
								<p>{selectedEntity.summary || 'No canon summary yet.'}</p>
								{selectedEntity.aliases.filter((alias) => alias.alias.toLocaleLowerCase() !== selectedEntity.name.toLocaleLowerCase()).length > 0 && <p className="cm-popover-aliases">Also known as {selectedEntity.aliases.filter((alias) => alias.alias.toLocaleLowerCase() !== selectedEntity.name.toLocaleLowerCase()).slice(0, 6).map((alias) => alias.alias).join(', ')}</p>}
								<button type="button" className="text-button" onClick={() => { onOpenEntityRef.current?.(selectedEntity.id); setPopover(null); }}>Open entity →</button>
							</>
						) : <p>This entity is no longer available.</p>)}
						{popover.kind === 'finding' && (selectedFinding ? (
							<>
								<div className="cm-popover-kicker">Line {selectedFinding.draft_line} · {selectedFinding.review_status} · {selectedFinding.confidence}% confidence</div>
								<p>{selectedFinding.explanation}</p>
								<blockquote>{selectedFinding.draft_quote}</blockquote>
								{selectedFinding.earlier_quote && <p className="cm-popover-earlier"><span>Earlier · Chapter {selectedFinding.earlier_chapter_number}</span>{selectedFinding.earlier_quote}</p>}
								<div className="cm-popover-actions">
									<button type="button" onClick={() => { onFindingActionRef.current?.(selectedFinding, 'resolve'); setPopover(null); }}>Resolve</button>
									<button type="button" onClick={() => { onFindingActionRef.current?.(selectedFinding, 'dismiss'); setPopover(null); }}>Dismiss</button>
									<button type="button" onClick={() => { onFindingActionRef.current?.(selectedFinding, 'intentional'); setPopover(null); }}>Intentional</button>
									<button type="button" onClick={() => { onOpenEvidenceRef.current?.(selectedFinding); setPopover(null); }}>Open evidence</button>
								</div>
							</>
						) : <p>This finding is no longer available.</p>)}
					</div>
				)}
			</div>
		);
	},
);

export default ManuscriptEditor;