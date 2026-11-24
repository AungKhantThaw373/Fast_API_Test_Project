import { describe, expect, it } from 'vitest';
import { retryDelayMs, saveStatus, shouldRetry } from '../save-state';

describe('save status labels', () => {
	it('maps each state to one label', () => {
		expect(saveStatus({ status: 'saved', revision: 2 }).label).toBe('Saved');
		expect(saveStatus({ status: 'saving', revision: 2 }).label).toBe('Saving…');
		expect(saveStatus({ status: 'dirty' }).label).toBe('Unsaved changes');
		expect(saveStatus({ status: 'offline', pending: true }).label).toBe('Offline · saved locally');
		expect(saveStatus({ status: 'conflict', serverRevision: 3, localContent: '' }).label).toBe('Conflict');
		expect(saveStatus({ status: 'error', message: 'nope' }).label).toBe('Error');
	});
});

describe('retry policy', () => {
	it('backs off exponentially and caps at 30s', () => {
		expect([0, 1, 2, 3, 4, 5, 6].map(retryDelayMs)).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
	});

	it('retries network, 429, and 5xx but not 4xx', () => {
		expect(shouldRetry(0)).toBe(true);
		expect(shouldRetry(429)).toBe(true);
		expect(shouldRetry(500)).toBe(true);
		expect(shouldRetry(404)).toBe(false);
		expect(shouldRetry(409)).toBe(false);
		expect(shouldRetry(422)).toBe(false);
	});
});
