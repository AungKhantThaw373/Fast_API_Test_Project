import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';

import type { ContinuityFinding } from '@/lib/api';
import { findingRange } from '@/lib/manuscript-decorations';

function finding(overrides: Partial<ContinuityFinding>): ContinuityFinding {
	return {
		id: 'finding',
		draft_quote: '',
		draft_line: 1,
		earlier_quote: '',
		earlier_chapter_id: 'chapter',
		earlier_chapter_number: 1,
		earlier_chapter_title: 'Earlier',
		explanation: '',
		confidence: 0.9,
		intentional: false,
		review_status: 'open',
		...overrides,
	};
}

describe('findingRange', () => {
	it('locates the quote on its recorded line', () => {
		const state = EditorState.create({ doc: 'First line\nMira had blue eyes.\nLast line' });
		const range = findingRange(state, finding({ draft_line: 2, draft_quote: 'blue eyes' }));
		expect(state.sliceDoc(range.from, range.to)).toBe('blue eyes');
	});

	it('falls back to a document search when the line moved', () => {
		const state = EditorState.create({ doc: 'Mira had blue eyes.\nA new first line.' });
		const range = findingRange(state, finding({ draft_line: 2, draft_quote: 'blue eyes' }));
		expect(state.sliceDoc(range.from, range.to)).toBe('blue eyes');
	});

	it('marks the whole line when the quote is gone', () => {
		const state = EditorState.create({ doc: 'Only this line.' });
		const range = findingRange(state, finding({ draft_line: 1, draft_quote: 'missing words' }));
		expect(state.sliceDoc(range.from, range.to)).toBe('Only this line.');
	});
});