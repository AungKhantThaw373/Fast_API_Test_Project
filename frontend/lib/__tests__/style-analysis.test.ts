import { describe, expect, it } from 'vitest';

import { analyzeStyle } from '@/lib/style-analysis';

describe('analyzeStyle', () => {
	it('finds crutch, filter, and adverb words at their exact offsets', () => {
		const text = 'She really noticed the door and quickly left. Only the nearly quiet room remained.';
		const report = analyzeStyle(text, 'chapter-1');
		const categories = report.issues.map((issue) => issue.category);
		expect(categories).toContain('crutch');
		expect(categories).toContain('filter');
		expect(categories).toContain('adverb');
		const adverb = report.issues.find((issue) => issue.category === 'adverb');
		expect(adverb && text.slice(adverb.start, adverb.end)).toBe('quickly');
		expect(report.issues.filter((issue) => issue.category === 'crutch').every((issue) => !issue.message.includes('nearly'))).toBe(true);
		expect(report.issues.every((issue) => issue.id.startsWith('chapter-1:'))).toBe(true);
	});

	it('finds repeated sentence openings', () => {
		const text = 'She walked to the window. She walked back. She walked outside. Rain fell. The room was cold. He waited.';
		const report = analyzeStyle(text);
		const openings = report.issues.filter((issue) => issue.category === 'opening');
		expect(openings).toHaveLength(2);
		expect(openings[0].message).toContain('She walked');
	});

	it('approximates passive constructions without flagging adjectives', () => {
		const text = 'The letter was taken before dawn. She was tired. The path was covered in leaves.';
		const report = analyzeStyle(text);
		const passive = report.issues.filter((issue) => issue.category === 'passive').map((issue) => text.slice(issue.start, issue.end));
		expect(passive.join(' ')).toContain('was taken');
		expect(passive.join(' ')).toContain('was covered');
		expect(passive.join(' ')).not.toContain('was tired');
	});

	it('flags a first-person pronoun in a third-person chapter', () => {
		const text = 'He walked into the hall. She followed him. They waited by the door. He checked his watch. She took her coat. They heard the bell. He said nothing. She looked away. I knew then.';
		const report = analyzeStyle(text);
		const pov = report.issues.filter((issue) => issue.category === 'pov');
		expect(pov).toHaveLength(1);
		expect(pov[0].excerpt).toContain('I');
	});

	it('does not treat dialogue pronouns as point-of-view slips', () => {
		const text = 'He walked into the hall. "I know," she said. He nodded. She waited. They left. He turned. She smiled. He waved. They went home.';
		const report = analyzeStyle(text);
		expect(report.issues.filter((issue) => issue.category === 'pov')).toHaveLength(0);
	});

	it('reports long paragraphs and readability statistics', () => {
		const paragraph = Array.from({ length: 170 }, () => 'word').join(' ');
		const report = analyzeStyle(`${paragraph}`, 'long');
		expect(report.stats.words).toBe(170);
		expect(report.stats.longestParagraphWords).toBe(170);
		expect(report.issues.some((issue) => issue.category === 'paragraph')).toBe(true);
		expect(report.stats.fleschKincaidGrade).toBeGreaterThanOrEqual(0);
		expect(report.stats.fleschReadingEase).toBeLessThanOrEqual(100);
	});

	it('flags a present-tense paragraph in a past-tense chapter', () => {
		const text = 'He walked to the door. She waited outside. They had left the lamp. He opened it. She looked back.\n\nHe is certain now. She has the key. They are ready.';
		const report = analyzeStyle(text);
		const tense = report.issues.filter((issue) => issue.category === 'tense');
		expect(tense.length).toBeGreaterThan(0);
		expect(tense[0].message).toContain('Present-tense');
	});
});