export type StyleCategory =
	| 'crutch'
	| 'adverb'
	| 'filter'
	| 'opening'
	| 'dialogue'
	| 'passive'
	| 'pov'
	| 'tense'
	| 'paragraph'
	| 'readability';

export interface StyleIssue {
	id: string;
	category: StyleCategory;
	start: number;
	end: number;
	line: number;
	excerpt: string;
	message: string;
	patternId: string;
}

export interface StyleStats {
	words: number;
	sentences: number;
	paragraphs: number;
	syllables: number;
	averageSentenceWords: number;
	fleschReadingEase: number;
	fleschKincaidGrade: number;
	dialogueTags: number;
	longestParagraphWords: number;
}

export interface StyleReport {
	issues: StyleIssue[];
	stats: StyleStats;
}

const CRUTCH_WORDS = ['just', 'really', 'very', 'actually', 'basically', 'simply', 'quite', 'somewhat', 'rather', 'perhaps', 'maybe', 'suddenly', 'literally', 'honestly', 'clearly', 'obviously', 'truly', 'definitely', 'absolutely', 'totally'];
const FILTER_WORDS = ['saw', 'heard', 'felt', 'noticed', 'realized', 'realised', 'seemed', 'watched', 'thought', 'wondered', 'knew', 'decided', 'looked', 'smelled', 'smelt', 'tasted'];
const DIALOGUE_TAGS = ['said', 'asked', 'replied', 'answered', 'whispered', 'muttered', 'shouted', 'exclaimed', 'cried', 'murmured', 'added', 'continued', 'began', 'snapped', 'growled', 'offered', 'admitted'];
const CRUTCH_SET = new Set(CRUTCH_WORDS);
const NON_ADVERBS = new Set(['only', 'family', 'early', 'friendly', 'lovely', 'lonely', 'silly', 'ugly', 'likely', 'daily', 'weekly', 'monthly', 'yearly', 'holy', 'jelly', 'belly', 'ally', 'bully', 'rally', 'tally', 'valley', 'fully', 'supply', 'apply', 'reply', 'multiply', 'imply', 'comply', 'fly', 'rely', 'assembly', 'anomaly', 'monopoly', 'melancholy']);
const PASSIVE_IRREGULARS = new Set(['known', 'seen', 'done', 'given', 'taken', 'made', 'written', 'held', 'kept', 'found', 'shown', 'told', 'brought', 'thought', 'caught', 'built', 'sent', 'left', 'paid', 'met', 'read', 'run', 'gone', 'come', 'become']);
const PASSIVE_ADJECTIVES = new Set(['red', 'bed', 'need', 'seed', 'feed', 'speed', 'indeed', 'hundred', 'sacred', 'wicked', 'naked', 'tired', 'worried', 'scared', 'pleased', 'interested', 'excited', 'married']);
const PRESENT_MARKERS = /\b(?:is|are|am|has|have|does|do|says|goes|walks|looks|feels|seems|takes|makes|knows|wants|needs|keeps|leaves|finds|thinks|watches|turns|opens|closes|stands|sits)\b/gi;
const PAST_MARKERS = /\b(?:was|were|had|did|said|went|walked|looked|felt|seemed|took|made|knew|wanted|needed|kept|left|found|thought|watched|turned|opened|closed|stood|sat)\b/gi;

interface Sentence { text: string; start: number; end: number; }
interface Paragraph { text: string; start: number; end: number; }
interface Match { text: string; start: number; end: number; }

function lineStarts(text: string): number[] {
	const starts = [0];
	for (let index = 0; index < text.length; index += 1) {
		if (text[index] === '\n') starts.push(index + 1);
	}
	return starts;
}

function lineAt(starts: number[], offset: number): number {
	let low = 0;
	let high = starts.length - 1;
	while (low <= high) {
		const middle = Math.floor((low + high) / 2);
		if (starts[middle] <= offset) low = middle + 1;
		else high = middle - 1;
	}
	return Math.max(1, high + 1);
}

function excerptAround(text: string, start: number, end: number): string {
	const from = Math.max(0, start - 28);
	const to = Math.min(text.length, end + 28);
	return `${from > 0 ? '…' : ''}${text.slice(from, to).replace(/\s+/g, ' ').trim()}${to < text.length ? '…' : ''}`;
}

function collect(text: string, regex: RegExp): Match[] {
	const found: Match[] = [];
	for (const match of text.matchAll(regex)) {
		if (match.index === undefined) continue;
		found.push({ text: match[0], start: match.index, end: match.index + match[0].length });
	}
	return found;
}

function sentencesOf(text: string): Sentence[] {
	const found: Sentence[] = [];
	const regex = /[^.!?]+(?:[.!?]+[\"'”’)\]]*)?|[.!?]+[\"'”’)\]]*/g;
	for (const match of text.matchAll(regex)) {
		if (match.index === undefined) continue;
		const raw = match[0];
		const leading = raw.length - raw.trimStart().length;
		const value = raw.trim();
		if (!value) continue;
		found.push({ text: value, start: match.index + leading, end: match.index + leading + value.length });
	}
	return found;
}

function paragraphsOf(text: string): Paragraph[] {
	const found: Paragraph[] = [];
	const regex = /[^\n]+(?:\n(?!\s*\n)[^\n]+)*/g;
	for (const match of text.matchAll(regex)) {
		if (match.index === undefined) continue;
		const raw = match[0];
		const leading = raw.length - raw.trimStart().length;
		const value = raw.trim();
		if (!value) continue;
		found.push({ text: value, start: match.index + leading, end: match.index + leading + value.length });
	}
	return found;
}

function syllables(word: string): number {
	const clean = word.toLocaleLowerCase().replace(/[^a-z]/g, '');
	if (!clean) return 0;
	if (clean.length <= 3) return 1;
	const groups = clean.replace(/(?:[^laeiouy]es|[^laeiouy]e)$/, '').replace(/^y/, '').match(/[aeiouy]{1,2}/g);
	return Math.max(1, groups?.length ?? 1);
}

function quotedIntervals(text: string): Array<[number, number]> {
	const intervals: Array<[number, number]> = [];
	for (const match of text.matchAll(/"[^"\n]*"|“[^”\n]*”/g)) {
		if (match.index !== undefined) intervals.push([match.index, match.index + match[0].length]);
	}
	return intervals;
}

function outside(intervals: Array<[number, number]>, offset: number): boolean {
	return !intervals.some(([start, end]) => offset >= start && offset < end);
}

export function analyzeStyle(text: string, chapterId = 'chapter'): StyleReport {
	const issues: StyleIssue[] = [];
	const seen = new Set<string>();
	const starts = lineStarts(text);
	const add = (category: StyleCategory, start: number, end: number, message: string, patternId: string) => {
		const key = `${category}:${start}:${end}`;
		if (seen.has(key)) return;
		seen.add(key);
		issues.push({ id: `${chapterId}:${key}`, category, start, end, line: lineAt(starts, start), excerpt: excerptAround(text, start, end), message, patternId });
	};

	for (const match of collect(text, new RegExp(`\\b(?:${CRUTCH_WORDS.join('|')})\\b`, 'gi'))) {
		add('crutch', match.start, match.end, `“${match.text}” is a crutch word. Try cutting it and see whether the sentence still carries.`, `crutch:${match.text.toLocaleLowerCase()}`);
	}

	for (const match of collect(text, /\b[\p{L}]{4,}ly\b/gu)) {
		const lower = match.text.toLocaleLowerCase();
		if (NON_ADVERBS.has(lower) || CRUTCH_SET.has(lower)) continue;
		add('adverb', match.start, match.end, `Adverb “${match.text}”. A stronger verb may do the same work.`, `adverb:${lower}`);
	}

	for (const match of collect(text, new RegExp(`\\b(?:${FILTER_WORDS.join('|')})\\b`, 'gi'))) {
		add('filter', match.start, match.end, `Filter word “${match.text}” puts a character between the reader and the moment.`, `filter:${match.text.toLocaleLowerCase()}`);
	}

	const sentences = sentencesOf(text);
	const openings = new Map<string, Sentence[]>();
	for (const sentence of sentences) {
		const twoWords = sentence.text.replace(/^[\s\"“'‘]+/, '').split(/\s+/).slice(0, 2).join(' ').toLocaleLowerCase().replace(/[^\p{L}\s'-]/gu, '');
		if (!twoWords.trim()) continue;
		const list = openings.get(twoWords) ?? [];
		list.push(sentence);
		openings.set(twoWords, list);
	}
	if (sentences.length >= 6) {
		for (const [opening, list] of openings) {
			if (list.length < 3) continue;
			const display = opening.charAt(0).toLocaleUpperCase() + opening.slice(1);
			for (const sentence of list.slice(1)) {
				add('opening', sentence.start, sentence.end, `${list.length} sentences open with “${display}”. Vary the entry into the scene.`, `opening:${opening}`);
			}
		}
	}

	const tagMatches: Array<{ tag: string; start: number; end: number }> = [];
	const tagRegex = new RegExp(`["“][^"”\\n]{1,400}["”]\\s*(?:,\\s*)?(${DIALOGUE_TAGS.join('|')})\\b`, 'gi');
	for (const match of text.matchAll(tagRegex)) {
		if (match.index === undefined || !match[1]) continue;
		const tag = match[1].toLocaleLowerCase();
		const start = match.index + match[0].toLocaleLowerCase().lastIndexOf(tag);
		tagMatches.push({ tag, start, end: start + tag.length });
	}
	if (tagMatches.length >= 4) {
		const counts = new Map<string, number>();
		for (const item of tagMatches) counts.set(item.tag, (counts.get(item.tag) ?? 0) + 1);
		const [dominant, count] = [...counts.entries()].sort((left, right) => right[1] - left[1])[0];
		if (count >= 3 && count / tagMatches.length >= 0.5) {
			for (const item of tagMatches.filter((tag) => tag.tag === dominant)) {
				add('dialogue', item.start, item.end, `“${dominant}” carries ${count} of ${tagMatches.length} dialogue tags. Use action beats or silence for variety.`, `dialogue:${dominant}`);
			}
		}
	}

	for (const match of text.matchAll(/\b(was|were|is|are|been|being|be)\s+([\p{L}]+)\b/giu)) {
		if (match.index === undefined || !match[2]) continue;
		const participle = match[2].toLocaleLowerCase();
		if (!PASSIVE_IRREGULARS.has(participle) && !(participle.length > 3 && participle.endsWith('ed'))) continue;
		if (PASSIVE_ADJECTIVES.has(participle)) continue;
		add('passive', match.index, match.index + match[0].length, `Possible passive construction: “${match[0]}”. Name the actor when it matters.`, 'passive');
	}

	const intervals = quotedIntervals(text);
	const firstPerson = collect(text, /\b(?:I|me|my|mine|myself)\b/g).filter((match) => outside(intervals, match.start));
	const thirdPerson = collect(text, /\b(?:he|him|his|she|her|hers|they|them|their|theirs)\b/gi).filter((match) => outside(intervals, match.start));
	if (thirdPerson.length >= 8 && thirdPerson.length > firstPerson.length * 3) {
		for (const match of firstPerson) {
			add('pov', match.start, match.end, `First-person “${match.text}” inside a predominantly third-person chapter. Check the point of view.`, 'pov:first');
		}
	}

	const paragraphs = paragraphsOf(text);
	const presentMarkers = collect(text, PRESENT_MARKERS).filter((match) => outside(intervals, match.start));
	const pastMarkers = collect(text, PAST_MARKERS).filter((match) => outside(intervals, match.start));
	if (pastMarkers.length >= presentMarkers.length * 1.5 && presentMarkers.length >= 2) {
		for (const paragraph of paragraphs) {
			const present = presentMarkers.filter((match) => match.start >= paragraph.start && match.end <= paragraph.end);
			const past = pastMarkers.filter((match) => match.start >= paragraph.start && match.end <= paragraph.end);
			if (present.length >= 2 && past.length === 0) {
				add('tense', present[0].start, present[0].end, `Present-tense verbs in a past-tense chapter (${present.length} in this paragraph). Check for a tense slip.`, 'tense:present');
			}
		}
	} else if (presentMarkers.length >= pastMarkers.length * 1.5 && pastMarkers.length >= 2) {
		for (const paragraph of paragraphs) {
			const present = presentMarkers.filter((match) => match.start >= paragraph.start && match.end <= paragraph.end);
			const past = pastMarkers.filter((match) => match.start >= paragraph.start && match.end <= paragraph.end);
			if (past.length >= 2 && present.length === 0) {
				add('tense', past[0].start, past[0].end, `Past-tense verbs in a present-tense chapter (${past.length} in this paragraph). Check for a tense slip.`, 'tense:past');
			}
		}
	}

	let longestParagraphWords = 0;
	for (const paragraph of paragraphs) {
		const paragraphWords = paragraph.text.match(/[\p{L}\p{N}'’-]+/gu)?.length ?? 0;
		longestParagraphWords = Math.max(longestParagraphWords, paragraphWords);
		if (paragraphWords > 160) {
			const firstWords = paragraph.text.slice(0, 48).replace(/\s+/g, ' ');
			add('paragraph', paragraph.start, Math.min(paragraph.end, paragraph.start + 48), `Paragraph runs ${paragraphWords} words. Consider a paragraph break after “${firstWords}…”.`, 'paragraph:long');
		}
	}

	const wordMatches = text.match(/[\p{L}\p{N}'’-]+/gu) ?? [];
	const words = wordMatches.length;
	const sentenceCount = Math.max(1, sentences.length);
	const syllableCount = wordMatches.reduce((total, word) => total + syllables(word), 0);
	const averageSentenceWords = words / sentenceCount;
	const ease = words === 0 ? 0 : 206.835 - 1.015 * averageSentenceWords - 84.6 * (syllableCount / Math.max(1, words));
	const grade = words === 0 ? 0 : 0.39 * averageSentenceWords + 11.8 * (syllableCount / Math.max(1, words)) - 15.59;

	issues.sort((left, right) => left.start - right.start || left.category.localeCompare(right.category));
	return {
		issues: issues.slice(0, 600),
		stats: {
			words,
			sentences: sentences.length,
			paragraphs: paragraphs.length,
			syllables: syllableCount,
			averageSentenceWords: Number(averageSentenceWords.toFixed(1)),
			fleschReadingEase: Number(Math.max(0, Math.min(100, ease)).toFixed(1)),
			fleschKincaidGrade: Number(Math.max(0, grade).toFixed(1)),
			dialogueTags: tagMatches.length,
			longestParagraphWords,
		},
	};
}

export const STYLE_CATEGORY_LABELS: Record<StyleCategory, string> = {
	crutch: 'Crutch words',
	adverb: 'Adverbs',
	filter: 'Filter words',
	opening: 'Repeated openings',
	dialogue: 'Dialogue tags',
	passive: 'Passive voice',
	pov: 'Point of view',
	tense: 'Tense',
	paragraph: 'Paragraph length',
	readability: 'Readability',
};