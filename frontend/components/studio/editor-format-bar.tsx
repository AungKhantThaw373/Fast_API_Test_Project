"use client";

import type { ManuscriptFormat } from "@/components/manuscript-editor";

const INKS = [
	{ name: "Ink", value: "#2b2a24" },
	{ name: "Rust", value: "#a3543e" },
	{ name: "Moss", value: "#49624c" },
	{ name: "Ochre", value: "#8a6232" },
	{ name: "Blue", value: "#3f6480" },
];

export function EditorFormatBar({ onFormat }: { onFormat: (command: ManuscriptFormat, color?: string) => void }) {
	const button = (command: ManuscriptFormat, label: string, glyph: string, title: string) => (
		<button
			type="button"
			className="format-button"
			aria-label={label}
			title={title}
			onMouseDown={(event) => event.preventDefault()}
			onClick={() => onFormat(command)}
		>
			{glyph}
		</button>
	);
	return (
		<div className="editor-format-bar" role="toolbar" aria-label="Text formatting">
			{button("bold", "Bold", "B", "Bold (Markdown **)" )}
			{button("italic", "Italic", "I", "Italic (Markdown *)" )}
			{button("underline", "Underline", "U", "Underline" )}
			{button("strike", "Strikethrough", "S", "Strikethrough" )}
			<span className="format-divider" aria-hidden="true" />
			{button("h2", "Heading", "H2", "Section heading" )}
			{button("quote", "Block quote", "“", "Block quote" )}
			{button("bullet", "Bulleted list", "•", "Bulleted list" )}
			{button("highlight", "Highlight", "▰", "Highlight" )}
			<details className="format-colors">
				<summary aria-label="Text color" title="Text color"><span>A</span><i /></summary>
				<div className="format-color-menu">
					<span>Ink color</span>
					{INKS.map((ink) => (
						<button
							key={ink.value}
							type="button"
							className="format-color-swatch"
							style={{ background: ink.value }}
							aria-label={`${ink.name} text`}
							title={ink.name}
							onMouseDown={(event) => event.preventDefault()}
							onClick={(event) => {
								onFormat("color", ink.value);
								event.currentTarget.closest("details")?.removeAttribute("open");
							}}
						/>
					))}
				</div>
			</details>
			{button("clear", "Clear formatting", "×", "Clear inline formatting" )}
		</div>
	);
}
