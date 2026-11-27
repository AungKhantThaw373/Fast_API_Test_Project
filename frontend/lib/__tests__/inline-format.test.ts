import { describe, expect, it } from 'vitest';

import { inlineMarks, parseInlineLine, type InlinePair } from '../inline-format';

function kinds(pairs: InlinePair[]): string[] {
	return pairs.map((pair) => pair.style.kind).sort();
}

function content(text: string, pair: InlinePair): string {
	return text.slice(pair.open.to, pair.close.from);
}

describe('inline formatting parser', () => {
	it('pairs the flat marks the toolbar produces', () => {
		const text = '**bold** and *soft* and ~~gone~~ and ==lit== and <u>line</u>';
		const pairs = parseInlineLine(text, 0);
		expect(kinds(pairs)).toEqual(['bold', 'highlight', 'italic', 'strike', 'underline']);
		for (const pair of pairs) {
			expect(content(text, pair)).not.toMatch(/\*\*|~~|==|<\/?u>/);
		}
	});

	it('keeps nested marks paired so their delimiters can be hidden', () => {
		const text = '**bold text***<u>~~italic text~~</u>*==';
		const pairs = parseInlineLine(text, 0);
		expect(kinds(pairs)).toEqual(['bold', 'italic', 'strike', 'underline']);
		expect(content(text, pairs.find((pair) => pair.style.kind === 'strike')!)).toBe('italic text');
		expect(pairs.some((pair) => pair.style.kind === 'highlight')).toBe(false);

		const marks = inlineMarks(pairs);
		expect(marks.length).toBeGreaterThan(0);
		for (const mark of marks) expect(text.slice(mark.from, mark.to)).not.toMatch(/\*\*|~~|==|<\/?u>/);
		expect(marks.some((mark) => mark.style.kind === 'italic' && text.slice(mark.from, mark.to) === 'italic text')).toBe(true);
	});

	it('treats ***text*** as bold and italic rather than stray asterisks', () => {
		const text = '***both***';
		const pairs = parseInlineLine(text, 0);
		expect(kinds(pairs)).toEqual(['bold', 'italic']);
		const marks = inlineMarks(pairs);
		expect(marks.filter((mark) => text.slice(mark.from, mark.to) === 'both')).toHaveLength(2);
	});

	it('does not mistake bold asterisks for an italic wrapper', () => {
		const text = '**bold** and *soft*';
		const pairs = parseInlineLine(text, 0);
		expect(kinds(pairs)).toEqual(['bold', 'italic']);
		expect(content(text, pairs.find((pair) => pair.style.kind === 'bold')!)).toBe('bold');
		expect(content(text, pairs.find((pair) => pair.style.kind === 'italic')!)).toBe('soft');
	});

	it('parses colored spans and leaves a lone marker visible', () => {
		const text = '<span style="color:#b91c1c">red</span> ==';
		const pairs = parseInlineLine(text, 0);
		expect(pairs).toHaveLength(1);
		expect(pairs[0].style).toMatchObject({ kind: 'color', color: '#b91c1c' });
		expect(content(text, pairs[0])).toBe('red');
	});

	it('applies offsets relative to the line start', () => {
		const text = '**bold**';
		const pairs = parseInlineLine(text, 40);
		expect(pairs[0].open).toMatchObject({ from: 40, to: 42 });
		expect(pairs[0].close).toMatchObject({ from: 46, to: 48 });
	});
});
