import type { WikiEntity } from '@/lib/api';

export interface EntityMatch {
	start: number;
	end: number;
	entityId: string;
	name: string;
	matched: string;
}

export interface EntityMatcher {
	find: (text: string) => EntityMatch[];
	size: number;
}

interface Pattern {
	entityId: string;
	name: string;
	alias: string;
	length: number;
	priority: number;
}

interface TrieNode {
	next: Map<string, TrieNode>;
	fail: TrieNode;
	outputs: Pattern[];
}

function node(): TrieNode {
	return { next: new Map(), fail: null as unknown as TrieNode, outputs: [] };
}

const WORD_CHARACTER = /[\p{L}\p{N}_]/u;

function isWordCharacter(character: string | undefined): boolean {
	return character !== undefined && WORD_CHARACTER.test(character);
}

/**
 * Aho-Corasick over entity names and aliases. Matching is case-insensitive
 * and only accepts whole words, so "Mira" never lights up inside "miracle".
 * Overlaps resolve to the longest match at the earliest position.
 */
export function buildEntityMatcher(entities: WikiEntity[]): EntityMatcher {
	const root = node();
	root.fail = root;
	const patterns: Pattern[] = [];
	for (const entity of entities) {
		if (entity.status !== 'active') continue;
		const seen = new Set<string>();
		const candidates: Array<{ alias: string; priority: number }> = [
			{ alias: entity.name, priority: 2 },
			...entity.aliases.map((alias) => ({ alias: alias.alias, priority: 1 })),
		];
		for (const candidate of candidates) {
			const alias = candidate.alias.trim();
			const lower = alias.toLocaleLowerCase();
			if (lower.length < 2 || seen.has(lower)) continue;
			seen.add(lower);
			const pattern: Pattern = { entityId: entity.id, name: entity.name, alias: lower, length: lower.length, priority: candidate.priority };
			patterns.push(pattern);
			let cursor = root;
			for (const character of lower) {
				let next = cursor.next.get(character);
				if (!next) {
					next = node();
					next.fail = root;
					cursor.next.set(character, next);
				}
				cursor = next;
			}
			cursor.outputs.push(pattern);
		}
	}

	const queue: TrieNode[] = [];
	for (const child of root.next.values()) {
		child.fail = root;
		queue.push(child);
	}
	for (let index = 0; index < queue.length; index += 1) {
		const current = queue[index];
		for (const [character, child] of current.next) {
			let fallback = current.fail;
			while (fallback !== root && !fallback.next.has(character)) fallback = fallback.fail;
			child.fail = fallback.next.get(character) ?? root;
			if (child.fail === child) child.fail = root;
			child.outputs = [...child.outputs, ...child.fail.outputs];
			queue.push(child);
		}
	}

	return {
		size: patterns.length,
		find(text: string) {
			if (!text || patterns.length === 0) return [];
			const lower = text.toLocaleLowerCase();
			if (lower.length !== text.length) {
				// Locale casing changed the string length; offsets would be unsafe.
				return [];
			}
			const found: EntityMatch[] = [];
			let cursor = root;
			for (let index = 0; index < lower.length; index += 1) {
				const character = lower[index];
				while (cursor !== root && !cursor.next.has(character)) cursor = cursor.fail;
				cursor = cursor.next.get(character) ?? root;
				for (const output of cursor.outputs) {
					const start = index - output.length + 1;
					const end = index + 1;
					if (start < 0) continue;
					if (isWordCharacter(text[start - 1]) || isWordCharacter(text[end])) continue;
					found.push({ start, end, entityId: output.entityId, name: output.name, matched: text.slice(start, end) });
				}
			}
			found.sort((left, right) => left.start - right.start || (right.end - right.start) - (left.end - left.start));
			const selected: EntityMatch[] = [];
			let lastEnd = -1;
			for (const match of found) {
				if (match.start < lastEnd) continue;
				selected.push(match);
				lastEnd = match.end;
				if (selected.length >= 2000) break;
			}
			return selected;
		},
	};
}