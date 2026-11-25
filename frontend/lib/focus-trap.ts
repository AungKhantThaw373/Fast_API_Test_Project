import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE = [
	'a[href]',
	'button:not([disabled])',
	'input:not([disabled]):not([type="hidden"])',
	'select:not([disabled])',
	'textarea:not([disabled])',
	'[tabindex]:not([tabindex="-1"])',
].join(',');

function focusable(container: HTMLElement) {
	return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((element) => element.offsetParent !== null);
}

/** Keep keyboard focus inside a modal and return it to the trigger on close. */
export function useFocusTrap<T extends HTMLElement>(active = true): RefObject<T | null> {
	const ref = useRef<T>(null);

	useEffect(() => {
		if (!active || !ref.current) return;
		const container = ref.current;
		const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		const overflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		const initial = container.querySelector<HTMLElement>('[data-autofocus]') ?? focusable(container)[0] ?? container;
		const timer = window.setTimeout(() => initial.focus(), 0);

		function onKeyDown(event: KeyboardEvent) {
			if (event.key !== 'Tab') return;
			const items = focusable(container);
			if (!items.length) {
				event.preventDefault();
				container.focus();
				return;
			}
			const first = items[0];
			const last = items[items.length - 1];
			const current = document.activeElement;
			if (event.shiftKey && (current === first || !container.contains(current))) {
				event.preventDefault();
				last.focus();
			} else if (!event.shiftKey && (current === last || !container.contains(current))) {
				event.preventDefault();
				first.focus();
			}
		}

		container.addEventListener('keydown', onKeyDown);
		return () => {
			window.clearTimeout(timer);
			container.removeEventListener('keydown', onKeyDown);
			document.body.style.overflow = overflow;
			previous?.focus();
		};
	}, [active]);

	return ref;
}