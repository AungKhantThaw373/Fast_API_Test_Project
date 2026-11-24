/** The save state is a state machine, not a boolean.
 *
 * The UI, the retry policy, and the conflict flow all read from this. Inferring
 * "are we saved?" from a pair of flags is how stale-revision loops happen.
 */

export type SaveState =
	| { status: 'saved'; revision: number }
	| { status: 'dirty' }
	| { status: 'saving'; revision: number }
	| { status: 'offline'; pending: boolean }
	| { status: 'conflict'; serverRevision: number; localContent: string }
	| { status: 'error'; message: string };

export type SaveStatusLabel =
	| 'Saved'
	| 'Saving…'
	| 'Unsaved changes'
	| 'Offline · saved locally'
	| 'Conflict'
	| 'Error';

export function saveStatus(state: SaveState): { label: SaveStatusLabel; tone: 'quiet' | 'busy' | 'attention' | 'error' } {
	switch (state.status) {
		case 'saved':
			return { label: 'Saved', tone: 'quiet' };
		case 'saving':
			return { label: 'Saving…', tone: 'busy' };
		case 'dirty':
			return { label: 'Unsaved changes', tone: 'attention' };
		case 'offline':
			return { label: 'Offline · saved locally', tone: 'attention' };
		case 'conflict':
			return { label: 'Conflict', tone: 'error' };
		case 'error':
			return { label: 'Error', tone: 'error' };
	}
}

/** Exponential backoff for network and 5xx failures: 1s, 2s, 4s, 8s, 16s, 30s. */
export function retryDelayMs(attempt: number): number {
	return Math.min(30_000, 1000 * 2 ** Math.max(0, attempt));
}

export function shouldRetry(status: number | undefined): boolean {
	// 0 = network failure (fetch threw), 5xx = server problem, 429 = slow down.
	return status === undefined || status === 0 || status === 429 || (status >= 500 && status <= 599);
}
