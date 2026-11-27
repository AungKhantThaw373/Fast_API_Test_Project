"use client";

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";
const THEME_EVENT = "stillroom:theme-change";

function currentTheme(): Theme {
	if (typeof document === "undefined") return "light";
	return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function subscribe(onChange: () => void) {
	window.addEventListener("storage", onChange);
	window.addEventListener(THEME_EVENT, onChange);
	return () => {
		window.removeEventListener("storage", onChange);
		window.removeEventListener(THEME_EVENT, onChange);
	};
}

/** The page paints before hydration, so layout.tsx installs the saved theme first. */
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
	const theme = useSyncExternalStore(subscribe, currentTheme, () => "light" as Theme);

	const toggle = () => {
		const next: Theme = currentTheme() === "dark" ? "light" : "dark";
		document.documentElement.dataset.theme = next;
		window.localStorage.setItem("stillroom:theme", next);
		window.dispatchEvent(new Event(THEME_EVENT));
	};

	return (
		<button
			type="button"
			className={"theme-toggle" + (compact ? " theme-toggle-compact" : "")}
			onClick={toggle}
			aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"}
			title={theme === "dark" ? "Light mode" : "Dark mode"}
			aria-pressed={theme === "dark"}
		>
			<span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
			{!compact && <span>{theme === "dark" ? "Light" : "Dark"}</span>}
		</button>
	);
}
