/** One-based line number for a character offset. Pure, so it is easy to test. */
export function lineNumberAt(text: string, offset: number): number {
	if (offset <= 0) return 1;
	return text.slice(0, Math.min(offset, text.length)).split("\n").length;
}

/** The text of one line, one-based, or an empty string when out of range. */
export function lineText(text: string, line: number): string {
	return text.split("\n")[line - 1] ?? "";
}

/** Character range covered by a one-based line, for selecting it in a textarea. */
export function lineRange(text: string, line: number): { start: number; end: number } {
	const lines = text.split("\n");
	const start = lines.slice(0, Math.max(0, line - 1)).reduce((total, value) => total + value.length + 1, 0);
	return { start, end: start + (lines[line - 1]?.length ?? 0) };
}
