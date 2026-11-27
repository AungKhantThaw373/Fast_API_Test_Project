import { describe, expect, it } from 'vitest';

import type { WikiEntity } from '@/lib/api';
import { buildEntityMatcher } from '@/lib/entity-matcher';

function entity(name: string, aliases: string[] = [], status: WikiEntity['status'] = 'active'): WikiEntity {
	return {
		id: name.toLowerCase().replaceAll(' ', '-'),
		story_id: 'story',
		entity_type: 'character',
		name,
		summary: '',
		status,
		merged_into_id: null,
		first_chapter_number: 1,
		last_chapter_number: 2,
		created_at: '',
		updated_at: '',
		aliases: aliases.map((alias, index) => ({
			id: `${name}-${index}`,
			alias,
			normalized_alias: alias.toLowerCase(),
			alias_type: 'name',
		})),
	};
}

describe('buildEntityMatcher', () => {
	it('matches whole names and aliases case-insensitively', () => {
		const matcher = buildEntityMatcher([entity('Mira Voss', ['Mira'])]);
		const matches = matcher.find('Mira crossed the yard. Later MIRA VOSS returned.');
		expect(matches.map((match) => match.matched)).toEqual(['Mira', 'MIRA VOSS']);
		expect(matches[0].entityId).toBe('mira-voss');
	});

	it('does not match inside another word', () => {
		const matcher = buildEntityMatcher([entity('Mira')]);
		expect(matcher.find('A miracle, a mirage, and Miranda.')).toEqual([]);
	});

	it('prefers the longest overlapping match', () => {
		const matcher = buildEntityMatcher([entity('The Gate', ['Gate'])]);
		const matches = matcher.find('The Gate opened.');
		expect(matches).toHaveLength(1);
		expect(matches[0].matched).toBe('The Gate');
	});

	it('ignores archived entities and one-character aliases', () => {
		const matcher = buildEntityMatcher([entity('Hollis', [], 'archived'), entity('Mira', ['M'])]);
		const matches = matcher.find('Hollis saw Mira and M.');
		expect(matches.map((match) => match.matched)).toEqual(['Mira']);
	});

	it('returns matches in document order', () => {
		const matcher = buildEntityMatcher([entity('Mira'), entity('Hollis')]);
		const matches = matcher.find('Hollis met Mira at the gate.');
		expect(matches.map((match) => match.matched)).toEqual(['Hollis', 'Mira']);
	});

	it('handles accented names without changing offsets', () => {
		const matcher = buildEntityMatcher([entity('Élodie')]);
		const matches = matcher.find('Élodie waited.');
		expect(matches[0].start).toBe(0);
		expect(matches[0].end).toBe(6);
	});
});