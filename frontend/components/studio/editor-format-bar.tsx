"use client";

import type { ManuscriptFormat } from "@/components/manuscript-editor";

const INKS = [
	{ name: "Ink", value: "#111827" },
	{ name: "Slate", value: "#475569" },
	{ name: "Blue", value: "#2563eb" },
	{ name: "Indigo", value: "#4f46e5" },
	{ name: "Cyan", value: "#0e7490" },
	{ name: "Amber", value: "#b45309" },
	{ name: "Coral", value: "#c2410c" },
	{ name: "Red", value: "#b91c1c" },
	{ name: "Rose", value: "#be123c" },
	{ name: "Plum", value: "#7e22ce" },
];

export function EditorFormatBar({
	onFormat,
	activeFormat,
}: {
	onFormat: (command: ManuscriptFormat, color?: string) => void;
	activeFormat?: ManuscriptFormat | null;
}) {
	const button = (command: ManuscriptFormat, label: string, glyph: string, title: string) => (
		<button
			type="button"
			className={`format-button${activeFormat === command ? " is-active" : ""}`}
			aria-label={label}
			aria-pressed={activeFormat === command}
			title={title}
			onMouseDown={(event) => event.preventDefault()}
			onClick={() => onFormat(command)}
		>
			{glyph}
		</button>
	);
	return (
		<div className="editor-format-bar" role="toolbar" aria-label="Text formatting">
			{button("bold", "Bold", "B", "Bold — Ctrl/Cmd+B or hold for the next words")}
			{button("italic", "Italic", "I", "Italic — Ctrl/Cmd+I or hold for the next words")}
			{button("underline", "Underline", "U", "Underline the selection or the next words")}
			{button("strike", "Strikethrough", "S", "Strike through the selection or the next words")}
			<span className="format-divider" aria-hidden="true" />
			{button("h2", "Heading", "H2", "Turn this line into a section heading" )}
			{button("highlight", "Highlight", "▰", "Highlight the selection or the next words")}
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
			<button
				type="button"
				className="format-button format-clear"
				aria-label="Clear formatting from the selected text"
				title="Clear formatting from the selected text"
				onMouseDown={(event) => event.preventDefault()}
				onClick={() => onFormat("clear")}
			>
				Clear
			</button>
		</div>
	);
}
