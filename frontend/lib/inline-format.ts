// Shared inline-format parser. It is deliberately independent of CodeMirror
// so the same pairing rules can be unit-tested outside the editor.

export type InlineStyle = {
	kind: 'bold' | 'italic' | 'strike' | 'highlight' | 'underline' | 'color';
	className: string;
	color?: string;
};

export type InlineMarker = { from: number; to: number; style: InlineStyle };
export type InlinePair = { open: InlineMarker; close: InlineMarker; style: InlineStyle };
type InlineToken = { from: number; to: number; style?: InlineStyle; stars?: number; closing?: boolean };

const BOLD: InlineStyle = { kind: 'bold', className: 'cm-format-bold' };
const ITALIC: InlineStyle = { kind: 'italic', className: 'cm-format-italic' };
const STRIKE: InlineStyle = { kind: 'strike', className: 'cm-format-strike' };
const HIGHLIGHT: InlineStyle = { kind: 'highlight', className: 'cm-format-highlight' };
const UNDERLINE: InlineStyle = { kind: 'underline', className: 'cm-format-underline' };

function readInlineTokens(text: string): InlineToken[] {
	const tokens: InlineToken[] = [];
	const tokenPattern = /<span style=["']color:(#[0-9a-fA-F]{3,8})["']>|<\/span>|<u>|<\/u>|(\*{1,})|~~|==/g;
	for (const match of text.matchAll(tokenPattern)) {
		if (match.index === undefined) continue;
		const from = match.index;
		const to = from + match[0].length;
		if (match[1]) {
			tokens.push({ from, to, style: { kind: 'color', className: 'cm-format-color', color: match[1] }, closing: false });
		} else if (match[0] === '</span>') {
			tokens.push({ from, to, style: { kind: 'color', className: 'cm-format-color' }, closing: true });
		} else if (match[0] === '<u>') {
			tokens.push({ from, to, style: UNDERLINE, closing: false });
		} else if (match[0] === '</u>') {
			tokens.push({ from, to, style: UNDERLINE, closing: true });
		} else if (match[2]) {
			tokens.push({ from, to, stars: match[2].length });
		} else if (match[0] === '~~') {
			tokens.push({ from, to, style: STRIKE });
		} else if (match[0] === '==') {
			tokens.push({ from, to, style: HIGHLIGHT });
		}
	}
	return tokens;
}

/**
 * Parse one line into matched, nested inline pairs. The old regex pass could
 * only render one style at a time and exposed the markers of a nested style,
 * which is how lines like **bold***<u>~~italic~~</u>* appeared in the editor.
 * This scanner keeps a style stack, handles *** as bold+italic, and hides only
 * delimiters that actually have a partner. A lone marker stays visible as text
 * instead of silently eating the writer's words.
 */
export function parseInlineLine(text: string, base: number): InlinePair[] {
	const stack: Array<{ style: InlineStyle; marker: InlineMarker }> = [];
	const pairs: InlinePair[] = [];

	const open = (style: InlineStyle, from: number, to: number) => {
		stack.push({ style, marker: { from: base + from, to: base + to, style } });
	};
	const close = (style: InlineStyle, from: number, to: number) => {
		const top = stack[stack.length - 1];
		if (!top || top.style.kind !== style.kind) return false;
		stack.pop();
		pairs.push({ open: top.marker, close: { from: base + from, to: base + to, style: top.style }, style: top.style });
		return true;
	};

	for (const token of readInlineTokens(text)) {
		if (token.stars) {
			let offset = 0;
			let remaining = token.stars;
			while (remaining > 0 && stack.length > 0) {
				const top = stack[stack.length - 1];
				const required = top.style.kind === 'bold' ? 2 : top.style.kind === 'italic' ? 1 : 0;
				if (!required || remaining < required) break;
				close(top.style, token.from + offset, token.from + offset + required);
				offset += required;
				remaining -= required;
			}
			while (remaining > 0) {
				if (remaining >= 3) {
					open(BOLD, token.from + offset, token.from + offset + 2);
					offset += 2;
					remaining -= 2;
					open(ITALIC, token.from + offset, token.from + offset + 1);
					offset += 1;
					remaining -= 1;
				} else if (remaining === 2) {
					open(BOLD, token.from + offset, token.from + offset + 2);
					offset += 2;
					remaining = 0;
				} else {
					open(ITALIC, token.from + offset, token.from + offset + 1);
					offset += 1;
					remaining = 0;
				}
			}
			continue;
		}
		if (!token.style) continue;
		if (token.closing) {
			close(token.style, token.from, token.to);
		} else if (stack.length > 0 && stack[stack.length - 1].style.kind === token.style.kind) {
			// ~~ and == are symmetric; a second marker closes the style on top.
			close(token.style, token.from, token.to);
		} else {
			open(token.style, token.from, token.to);
		}
	}

	return pairs;
}

export function inlineMarks(pairs: InlinePair[]): Array<{ from: number; to: number; style: InlineStyle }> {
	const markers = pairs.flatMap((pair) => [pair.open, pair.close]).sort((a, b) => a.from - b.from || a.to - b.to);
	const marks: Array<{ from: number; to: number; style: InlineStyle }> = [];
	for (const pair of pairs) {
		let cursor = pair.open.to;
		for (const marker of markers) {
			if (marker.from >= pair.close.from) break;
			if (marker.to <= cursor) continue;
			if (marker.from > cursor) marks.push({ from: cursor, to: marker.from, style: pair.style });
			cursor = Math.max(cursor, marker.to);
		}
		if (cursor < pair.close.from) marks.push({ from: cursor, to: pair.close.from, style: pair.style });
	}
	return marks;
}
