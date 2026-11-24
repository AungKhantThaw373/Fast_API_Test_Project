'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { useState } from 'react';

export type StoryNameDialogProps = {
	open: boolean;
	title: string;
	label: string;
	description?: string;
	initialValue: string;
	placeholder?: string;
	allowEmpty?: boolean;
	onSubmit: (value: string) => Promise<void> | void;
	onCancel: () => void;
};

/** Accessible replacement for `window.prompt`. */
export function StoryNameDialog(props: StoryNameDialogProps) {
	return (
		<Dialog.Root open={props.open} onOpenChange={(next) => { if (!next) props.onCancel(); }}>
			<Dialog.Portal>
				<Dialog.Overlay className="dialog-overlay" />
				<Dialog.Content className="dialog-card confirm-card" aria-describedby={props.description ? 'name-dialog-description' : undefined}>
					{/* Remount per opening so the field starts from the current value
					    without syncing state inside an effect. */}
					{props.open && <NameForm key={props.initialValue} {...props} />}
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}

function NameForm({ title, label, description, initialValue, placeholder, allowEmpty = false, onSubmit, onCancel }: StoryNameDialogProps) {
	const [value, setValue] = useState(initialValue);
	const [busy, setBusy] = useState(false);

	async function submit(event: React.FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (!allowEmpty && !value.trim()) return;
		setBusy(true);
		try {
			await onSubmit(value.trim());
		} finally {
			setBusy(false);
		}
	}

	return (
		<form onSubmit={submit}>
			<Dialog.Title className="dialog-title">{title}</Dialog.Title>
			{description && <Dialog.Description className="dialog-description" id="name-dialog-description">{description}</Dialog.Description>}
			<label className="ai-field">
				<span>{label}</span>
				<input
					value={value}
					onChange={(event) => setValue(event.target.value)}
					placeholder={placeholder}
					maxLength={200}
					autoFocus
				/>
			</label>
			<div className="dialog-actions">
				<Dialog.Close asChild>
					<button type="button" className="quiet-button" onClick={onCancel}>Cancel</button>
				</Dialog.Close>
				<button className="button button-primary" disabled={busy || (!allowEmpty && !value.trim())}>
					{busy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</form>
	);
}
