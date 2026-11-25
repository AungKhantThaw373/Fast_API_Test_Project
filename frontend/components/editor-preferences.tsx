"use client";

import * as Popover from '@radix-ui/react-popover';

import type { EditorPreferences, EditorTheme } from '@/lib/editor-preferences';

const THEMES: Array<{ value: EditorTheme; label: string }> = [
	{ value: 'paper', label: 'Paper' },
	{ value: 'sepia', label: 'Sepia' },
	{ value: 'night', label: 'Night' },
];

export function EditorPreferencesMenu({
	preferences,
	onChange,
}: {
	preferences: EditorPreferences;
	onChange: (next: EditorPreferences) => void;
}) {
	const set = <K extends keyof EditorPreferences>(key: K, value: EditorPreferences[K]) =>
		onChange({ ...preferences, [key]: value });

	return (
		<Popover.Root>
			<Popover.Trigger asChild>
				<button className="text-button editor-prefs-trigger" aria-label="Editor appearance and focus settings" title="Editor appearance">
					Aa
				</button>
			</Popover.Trigger>
			<Popover.Portal>
				<Popover.Content className="editor-prefs" sideOffset={8} align="end">
					<div className="editor-prefs-head">
						<strong>Editor</strong>
						<span>Saved on this device</span>
					</div>
					<label className="editor-prefs-row">
						<span>Typeface</span>
						<select value={preferences.fontFamily} onChange={(event) => set('fontFamily', event.target.value as 'serif' | 'sans')}>
							<option value="serif">Serif</option>
							<option value="sans">Sans</option>
						</select>
					</label>
					<label className="editor-prefs-row">
						<span>Size <output>{preferences.fontSize}px</output></span>
						<input type="range" min={14} max={32} step={1} value={preferences.fontSize} onChange={(event) => set('fontSize', Number(event.target.value))} />
					</label>
					<label className="editor-prefs-row">
						<span>Line height <output>{preferences.lineHeight.toFixed(2)}</output></span>
						<input type="range" min={1.3} max={2.4} step={0.05} value={preferences.lineHeight} onChange={(event) => set('lineHeight', Number(event.target.value))} />
					</label>
					<label className="editor-prefs-row">
						<span>Measure <output>{preferences.measure}px</output></span>
						<input type="range" min={480} max={1200} step={20} value={preferences.measure} onChange={(event) => set('measure', Number(event.target.value))} />
					</label>
					<label className="editor-prefs-row">
						<span>Theme</span>
						<select value={preferences.theme} onChange={(event) => set('theme', event.target.value as EditorTheme)}>
							{THEMES.map((theme) => <option key={theme.value} value={theme.value}>{theme.label}</option>)}
						</select>
					</label>
					<label className="editor-prefs-check">
						<input type="checkbox" checked={preferences.typewriter} onChange={(event) => set('typewriter', event.target.checked)} />
						<span>Typewriter mode <small>Keep the current line centred</small></span>
					</label>
					<label className="editor-prefs-check">
						<input type="checkbox" checked={preferences.focusMode} onChange={(event) => set('focusMode', event.target.checked)} />
						<span>Focus mode <small>Dim everything but this line</small></span>
					</label>
					<label className="editor-prefs-row">
						<span>Daily word goal</span>
						<input type="number" min={0} step={100} value={preferences.wordGoal} onChange={(event) => set('wordGoal', Math.max(0, Number(event.target.value) || 0))} />
					</label>
					<Popover.Close className="button button-approve editor-prefs-done">Done</Popover.Close>
				</Popover.Content>
			</Popover.Portal>
		</Popover.Root>
	);
}