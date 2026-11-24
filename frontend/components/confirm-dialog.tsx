'use client';

import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';

export type ConfirmOptions = {
	title: string;
	description?: string;
	confirmLabel?: string;
	cancelLabel?: string;
	destructive?: boolean;
};

type ConfirmContextValue = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

/** Accessible replacement for `window.confirm`.
 *
 * Radix traps focus, restores it on close, and wires Escape to cancel, which a
 * native confirm cannot do inside a React app.
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
	const [options, setOptions] = useState<ConfirmOptions | null>(null);
	const resolver = useRef<((value: boolean) => void) | null>(null);

	const confirm = useCallback<ConfirmContextValue>((next) => {
		resolver.current?.(false);
		setOptions(next);
		return new Promise<boolean>((resolve) => {
			resolver.current = resolve;
		});
	}, []);

	const settle = useCallback((value: boolean) => {
		resolver.current?.(value);
		resolver.current = null;
		setOptions(null);
	}, []);

	return (
		<ConfirmContext.Provider value={confirm}>
			{children}
			<AlertDialog.Root open={options !== null} onOpenChange={(open) => { if (!open) settle(false); }}>
				<AlertDialog.Portal>
					<AlertDialog.Overlay className="dialog-overlay" />
					<AlertDialog.Content className="dialog-card confirm-card" aria-describedby={options?.description ? 'confirm-description' : undefined}>
						<AlertDialog.Title className="dialog-title">{options?.title}</AlertDialog.Title>
						{options?.description && <AlertDialog.Description className="dialog-description" id="confirm-description">{options.description}</AlertDialog.Description>}
						<div className="dialog-actions">
							<AlertDialog.Cancel asChild>
								<button className="quiet-button" onClick={() => settle(false)}>{options?.cancelLabel ?? 'Cancel'}</button>
							</AlertDialog.Cancel>
							<AlertDialog.Action asChild>
								<button
									className={options?.destructive ? 'button button-destructive' : 'button button-primary'}
									onClick={() => settle(true)}
								>
									{options?.confirmLabel ?? 'Continue'}
								</button>
							</AlertDialog.Action>
						</div>
					</AlertDialog.Content>
				</AlertDialog.Portal>
			</AlertDialog.Root>
		</ConfirmContext.Provider>
	);
}

export function useConfirm(): ConfirmContextValue {
	const context = useContext(ConfirmContext);
	if (!context) throw new Error('useConfirm must be used inside ConfirmProvider');
	return context;
}
