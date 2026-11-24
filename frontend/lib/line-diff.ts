/** A minimal line diff: added/removed lines with line numbers.
 *
 * The editor only needs to show what changed; character-level highlighting is
 * noise. Long chapters fall back to a coarse summary instead of freezing the
 * main thread.
 */

export type DiffLine = {
	kind: 'same' | 'added' | 'removed';
	text: string;
	oldLine?: number;
	newLine?: number;
};

const MAX_LINES = 4000;

export function lineDiff(oldText: string, newText: string): DiffLine[] {
	const oldLines = oldText.split('\n');
	const newLines = newText.split('\n');
	if (oldLines.length > MAX_LINES || newLines.length > MAX_LINES) {
		return [
			{ kind: 'removed', text: `(old version: ${oldLines.length} lines)` },
			{ kind: 'added', text: `(new version: ${newLines.length} lines)` },
		];
	}

	// Classic LCS table. For chapter-sized documents this is fast enough and it
	// keeps the dependency surface at zero.
	const rows = oldLines.length;
	const cols = newLines.length;
	const table: Uint32Array = new Uint32Array((rows + 1) * (cols + 1));
	const at = (row: number, col: number) => row * (cols + 1) + col;
	for (let row = rows - 1; row >= 0; row -= 1) {
		for (let col = cols - 1; col >= 0; col -= 1) {
			table[at(row, col)] = oldLines[row] === newLines[col]
				? table[at(row + 1, col + 1)] + 1
				: Math.max(table[at(row + 1, col)], table[at(row, col + 1)]);
		}
	}

	const result: DiffLine[] = [];
	let row = 0;
	let col = 0;
	while (row < rows && col < cols) {
		if (oldLines[row] === newLines[col]) {
			result.push({ kind: 'same', text: oldLines[row], oldLine: row + 1, newLine: col + 1 });
			row += 1;
			col += 1;
		} else if (table[at(row + 1, col)] >= table[at(row, col + 1)]) {
			result.push({ kind: 'removed', text: oldLines[row], oldLine: row + 1 });
			row += 1;
		} else {
			result.push({ kind: 'added', text: newLines[col], newLine: col + 1 });
			col += 1;
		}
	}
	while (row < rows) {
		result.push({ kind: 'removed', text: oldLines[row], oldLine: row + 1 });
		row += 1;
	}
	while (col < cols) {
		result.push({ kind: 'added', text: newLines[col], newLine: col + 1 });
		col += 1;
	}
	return result;
}

/** Collapse long runs of unchanged lines so a diff stays readable. */
export function compactDiff(lines: DiffLine[], context = 3): DiffLine[] {
	const keep = new Set<number>();
	lines.forEach((line, index) => {
		if (line.kind === 'same') return;
		for (let offset = -context; offset <= context; offset += 1) {
			const target = index + offset;
			if (target >= 0 && target < lines.length) keep.add(target);
		}
	});
	if (keep.size === 0) return [];
	const output: DiffLine[] = [];
	let skipped = 0;
	lines.forEach((line, index) => {
		if (keep.has(index)) {
			if (skipped > 0) {
				output.push({ kind: 'same', text: `… ${skipped} unchanged line${skipped === 1 ? '' : 's'} …` });
				skipped = 0;
			}
			output.push(line);
		} else {
			skipped += 1;
		}
	});
	return output;
}
