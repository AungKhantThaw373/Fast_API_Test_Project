import { describe, expect, it } from 'vitest';

import {
	EMPTY_FILTERS,
	activeFilterLabels,
	entityTypeLabel,
	filtersForApi,
	hasActiveFilters,
	lastSeenLabel,
	normalizeEntityType,
	oneLineSummary,
	openThreadCount,
	parseFilters,
	summariseAliases,
	toSearchParams,
} from '@/components/wiki/wiki-filters';

describe('wiki filter URL state', () => {
	it('round-trips filters through search params', () => {
		const filters = { type: 'character', status: 'active', arc: '', q: 'mira' };
		expect(toSearchParams(filters)).toBe('?type=character&status=active&q=mira');
		expect(parseFilters(new URLSearchParams('type=character&status=active&q=mira'))).toEqual(filters);
	});

	it('drops empty values instead of writing blank params', () => {
		expect(toSearchParams(EMPTY_FILTERS)).toBe('');
		expect(toSearchParams({ ...EMPTY_FILTERS, q: '   ' })).toBe('');
	});

	it('reads the first value when Next hands over an array', () => {
		expect(parseFilters({ type: ['location', 'item'], q: undefined })).toEqual({
			type: 'location',
			status: '',
			arc: '',
			q: '',
		});
	});

	it('only sends filters the API understands', () => {
		expect(filtersForApi({ type: 'item', status: '', arc: '', q: ' lamp ' })).toEqual({ type: 'item', q: 'lamp' });
		expect(filtersForApi({ ...EMPTY_FILTERS, arc: 'arc-1' })).toEqual({ arc_id: 'arc-1' });
		expect(filtersForApi(EMPTY_FILTERS)).toEqual({});
	});

	it('describes active filters for the empty state', () => {
		expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false);
		expect(activeFilterLabels({ type: 'location', status: 'archived', arc: '', q: 'port' })).toEqual([
			'“port”',
			'Place',
			'Archived',
		]);
		expect(activeFilterLabels({ ...EMPTY_FILTERS, type: 'cursed_technique' })).toEqual(['Cursed technique']);
	});

	it('turns a novel-specific type label into a safe slug', () => {
		expect(normalizeEntityType('Cursed Technique')).toBe('cursed_technique');
		expect(normalizeEntityType('  ship-class!! ')).toBe('ship_class');
		expect(normalizeEntityType('9 lives')).toBe('type_9_lives');
		expect(normalizeEntityType('')).toBe('other');
		expect(entityTypeLabel('cursed_technique')).toBe('Cursed technique');
	});
});

describe('wiki row helpers', () => {
	it('caps aliases and reports the remainder', () => {
		const aliases = ['a', 'b', 'c', 'd'].map((alias) => ({ id: alias, alias, normalized_alias: alias, alias_type: 'name' as const }));
		expect(summariseAliases(aliases)).toEqual({ shown: ['a', 'b', 'c'], more: 1 });
		expect(summariseAliases([])).toEqual({ shown: [], more: 0 });
	});

	it('keeps summaries to one line and one length', () => {
		expect(oneLineSummary({ name: 'Mira', summary: '  A  captain\n of the watch. ' })).toBe('A captain of the watch.');
		expect(oneLineSummary({ name: 'Mira', summary: '' })).toBe('No summary yet for Mira.');
		expect(oneLineSummary({ name: 'X', summary: 'a'.repeat(200) }, 20)).toHaveLength(20);
	});

	it('labels the last appearance in plain words', () => {
		expect(lastSeenLabel({ last_chapter_number: 12, first_chapter_number: 3 })).toBe('Last seen ch. 12');
		expect(lastSeenLabel({ last_chapter_number: null, first_chapter_number: 3 })).toBe('First seen ch. 3');
		expect(lastSeenLabel({ last_chapter_number: null, first_chapter_number: null })).toBe('Not yet mentioned');
	});

	it('counts only unresolved threads that link the entity', () => {
		const threads = [
			{ state: 'open', linked_entity_ids: ['e1'] },
			{ state: 'touched', linked_entity_ids: ['e1', 'e2'] },
			{ state: 'resolved', linked_entity_ids: ['e1'] },
			{ state: 'abandoned', linked_entity_ids: ['e1'] },
			{ state: 'open', linked_entity_ids: ['e2'] },
		];
		expect(openThreadCount('e1', threads)).toBe(2);
		expect(openThreadCount('e3', threads)).toBe(0);
	});
});
