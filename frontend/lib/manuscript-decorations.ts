import { Decoration, EditorView, GutterMarker, gutter, type DecorationSet } from '@codemirror/view';
import { StateEffect, StateField, type EditorState, type Range } from '@codemirror/state';

import type { ContinuityFinding, WikiEntity } from '@/lib/api';
import type { EntityMatcher } from '@/lib/entity-matcher';
import type { StyleIssue } from '@/lib/style-analysis';

export interface AnnotationPayload {
	decorations: DecorationSet;
	findingsByLine: Map<number, ContinuityFinding[]>;
}

export const setAnnotations = StateEffect.define<AnnotationPayload>();

const EMPTY: AnnotationPayload = { decorations: Decoration.none, findingsByLine: new Map() };

export const annotationField = StateField.define<AnnotationPayload>({
	create: () => EMPTY,
	update(value, transaction) {
		for (const effect of transaction.effects) {
			if (effect.is(setAnnotations)) return effect.value;
		}
		if (!transaction.docChanged) return value;
		return { ...value, decorations: value.decorations.map(transaction.changes) };
	},
	provide: (field) => EditorView.decorations.from(field, (value) => value.decorations),
});

export function findingRange(state: EditorState, finding: ContinuityFinding): { from: number; to: number } {
	const lineNumber = Math.max(1, Math.min(finding.draft_line || 1, state.doc.lines));
	const line = state.doc.line(lineNumber);
	const quote = (finding.draft_quote ?? '').trim();
	if (!quote) return { from: line.from, to: line.to };
	const local = line.text.indexOf(quote);
	if (local >= 0) return { from: line.from + local, to: line.from + local + quote.length };
	const absolute = state.doc.toString().indexOf(quote);
	if (absolute >= 0) return { from: absolute, to: absolute + quote.length };
	return { from: line.from, to: line.to };
}

export function buildAnnotations(
	state: EditorState,
	matcher: EntityMatcher,
	entities: WikiEntity[],
	findings: ContinuityFinding[],
	styleIssues: StyleIssue[] = [],
): AnnotationPayload {
	const entityById = new Map(entities.map((entity) => [entity.id, entity]));
	const text = state.doc.toString();
	const ranges: Range<Decoration>[] = [];
	for (const match of matcher.find(text)) {
		const entity = entityById.get(match.entityId);
		if (!entity) continue;
		ranges.push(
			Decoration.mark({
				class: 'cm-entity-mark',
				attributes: {
					'data-entity-id': entity.id,
					'data-entity-name': entity.name,
					role: 'button',
					tabindex: '0',
					'aria-label': `${entity.name} canon card`,
				},
			}).range(match.start, match.end),
		);
	}
	for (const issue of styleIssues.slice(0, 600)) {
		if (issue.start < 0 || issue.end <= issue.start || issue.end > text.length) continue;
		ranges.push(
			Decoration.mark({
				class: 'cm-style-mark',
				attributes: {
					'data-style-id': issue.id,
					role: 'button',
					tabindex: '0',
					title: issue.message,
					'aria-label': `${issue.category}: ${issue.message}`,
				},
			}).range(issue.start, issue.end),
		);
	}
	const findingsByLine = new Map<number, ContinuityFinding[]>();
	for (const finding of findings.slice(0, 200)) {
		const range = findingRange(state, finding);
		// An empty line has no text to decorate. The gutter still records the
		// finding so it can be opened and navigated to.
		if (range.to > range.from) {
			ranges.push(
				Decoration.mark({
					class: 'cm-finding-mark',
					attributes: {
						'data-finding-id': finding.id,
						role: 'button',
						tabindex: '0',
						'aria-label': `Continuity finding on line ${finding.draft_line}`,
					},
				}).range(range.from, range.to),
			);
		}
		const lineNumber = state.doc.lineAt(range.from).number;
		const current = findingsByLine.get(lineNumber) ?? [];
		current.push(finding);
		findingsByLine.set(lineNumber, current);
	}
	return { decorations: Decoration.set(ranges, true), findingsByLine };
}

class FindingMarker extends GutterMarker {
	constructor(readonly findingId: string, readonly count: number) {
		super();
	}

	eq(other: GutterMarker): boolean {
		return other instanceof FindingMarker && other.findingId === this.findingId && other.count === this.count;
	}

	toDOM(): Node {
		const marker = document.createElement('button');
		marker.type = 'button';
		marker.className = 'cm-finding-gutter-dot';
		marker.dataset.findingId = this.findingId;
		marker.title = this.count > 1 ? `${this.count} continuity findings on this line` : 'Continuity finding';
		marker.setAttribute('aria-label', marker.title);
		marker.textContent = this.count > 1 ? String(this.count) : '';
		return marker;
	}
}

export function createFindingGutter(onFinding: (findingId: string) => void) {
	return gutter({
		class: 'cm-finding-gutter',
		lineMarkerChange: (update) => update.docChanged || update.transactions.some((transaction) => transaction.effects.some((effect) => effect.is(setAnnotations))),
		lineMarker(view, line) {
			const lineNumber = view.state.doc.lineAt(line.from).number;
			const findings = view.state.field(annotationField).findingsByLine.get(lineNumber);
			if (!findings?.length) return null;
			return new FindingMarker(findings[0].id, findings.length);
		},
		domEventHandlers: {
			click(view, line, event) {
				const target = event.target as HTMLElement | null;
				const button = target?.closest<HTMLElement>('[data-finding-id]');
				const lineNumber = view.state.doc.lineAt(line.from).number;
				const finding = view.state.field(annotationField).findingsByLine.get(lineNumber)?.[0];
				const id = button?.dataset.findingId ?? finding?.id;
				if (id) {
					onFinding(id);
					return true;
				}
				return false;
			},
		},
	});
}