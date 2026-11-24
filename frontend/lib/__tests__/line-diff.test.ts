import { describe, expect, it } from 'vitest';
import { compactDiff, lineDiff } from '../line-diff';

describe('lineDiff', () => {
	it('marks added and removed lines', () => {
		const diff = lineDiff('one\ntwo\nthree', 'one\nTWO\nthree');
		expect(diff.filter((line) => line.kind === 'removed').map((line) => line.text)).toEqual(['two']);
		expect(diff.filter((line) => line.kind === 'added').map((line) => line.text)).toEqual(['TWO']);
	});

	it('reports no changes for identical text', () => {
		const diff = lineDiff('same\ntext', 'same\ntext');
		expect(diff.every((line) => line.kind === 'same')).toBe(true);
	});

	it('tracks line numbers on both sides', () => {
		const diff = lineDiff('a\nb', 'a\nb\nc');
		const added = diff.find((line) => line.kind === 'added');
		expect(added?.newLine).toBe(3);
		expect(added?.oldLine).toBeUndefined();
	});

	it('degrades gracefully for very large documents', () => {
		const huge = Array.from({ length: 5000 }, (_, index) => `line ${index}`).join('\n');
		expect(lineDiff(huge, `${huge}\nextra`)).toEqual([
			{ kind: 'removed', text: '(old version: 5000 lines)' },
			{ kind: 'added', text: '(new version: 5001 lines)' },
		]);
	});
});

describe('compactDiff', () => {
	it('collapses long unchanged runs', () => {
		const before = Array.from({ length: 20 }, (_, index) => `line ${index}`).join('\n');
		const after = before.replace('line 10', 'line ten');
		const compact = compactDiff(lineDiff(before, after), 1);
		expect(compact.some((line) => line.text.includes('unchanged'))).toBe(true);
		expect(compact.some((line) => line.kind === 'removed' && line.text === 'line 10')).toBe(true);
		expect(compact.some((line) => line.kind === 'added' && line.text === 'line ten')).toBe(true);
	});

	it('returns nothing when nothing changed', () => {
		expect(compactDiff(lineDiff('same', 'same'))).toEqual([]);
	});
});
