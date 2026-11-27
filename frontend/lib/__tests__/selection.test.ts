import { describe, expect, it } from 'vitest';

import { lineNumberAt, lineRange, lineText } from '../selection';

const TEXT = "First line.\nSecond line has Mira.\nThird.";

describe('text selection helpers', () => {
	it('reports one-based line numbers for offsets', () => {
		expect(lineNumberAt(TEXT, 0)).toBe(1);
		expect(lineNumberAt(TEXT, 5)).toBe(1);
		expect(lineNumberAt(TEXT, 12)).toBe(2);
		expect(lineNumberAt(TEXT, TEXT.length)).toBe(3);
		expect(lineNumberAt(TEXT, 10_000)).toBe(3);
	});

	it('returns the text of a line and an empty string out of range', () => {
		expect(lineText(TEXT, 2)).toBe('Second line has Mira.');
		expect(lineText(TEXT, 9)).toBe('');
	});

	it('gives the character range that selects a line exactly', () => {
		const range = lineRange(TEXT, 2);
		expect(TEXT.slice(range.start, range.end)).toBe('Second line has Mira.');
		expect(lineRange(TEXT, 1)).toEqual({ start: 0, end: 11 });
	});
});
