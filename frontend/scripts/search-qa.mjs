// Find-in-story UI checks. Run against a built app and a live API + worker.
import { chromium } from "playwright";

const WEB = process.env.WEB_URL ?? "http://127.0.0.1:3000";
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const stamp = Date.now();
const PASSWORD = "correct horse battery";

async function request(path, options = {}, cookie) {
	const response = await fetch(`${API}${path}`, {
		...options,
		headers: { "Content-Type": "application/json", ...(cookie ? { Cookie: cookie } : {}), ...options.headers },
	});
	const text = await response.text();
	if (!response.ok) throw new Error(`${options.method ?? "GET"} ${path} -> ${response.status} ${text}`);
	return text ? JSON.parse(text) : null;
}

async function seed() {
	const email = `search${stamp}@example.com`;
	await request("/register", {
		method: "POST",
		body: JSON.stringify({ username: `search${stamp}`, email, password: PASSWORD }),
	});
	const response = await fetch(`${API}/token`, {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: new URLSearchParams({ username: email, password: PASSWORD }),
	});
	const cookie = (response.headers.get("set-cookie") ?? "").split(";")[0];
	if (!cookie) throw new Error("no session cookie");
	const story = await request("/stories", { method: "POST", body: JSON.stringify({ title: `Search QA ${stamp}` }) }, cookie);
	const chapters = [
		{ title: "The Lantern", content: "Mira Voss crossed the yard before dawn.\nThe lantern guttered in her hand.\nShe said nothing to Hollis." },
		{ title: "The Gate", content: "Hollis waited by the gate.\nRain drummed on the roof.\nThe road was empty." },
		{ title: "The Lighthouse", content: "At the lighthouse, Mira found the lantern again.\nIts glass was cracked.\nShe wrapped it in her coat." },
	];
	for (const chapter of chapters) {
		await request(`/stories/${story.id}/chapters`, { method: "POST", body: JSON.stringify(chapter) }, cookie);
	}
	return { email, cookie, story };
}

async function waitForIndex(storyId, cookie) {
	const deadline = Date.now() + 90_000;
	while (Date.now() < deadline) {
		const status = await request(`/stories/${storyId}/index-status`, {}, cookie);
		if (status.chapters.length && status.chapters.every((item) => item.index_status === "indexed")) return;
		if (status.chapters.some((item) => item.index_status === "failed")) throw new Error("indexing failed: " + JSON.stringify(status));
		await new Promise((resolve) => setTimeout(resolve, 1000));
	}
	throw new Error("indexing timed out");
}

const results = [];
function check(name, condition, detail = "") {
	results.push({ name, ok: Boolean(condition), detail });
	console.log(`${condition ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

async function main() {
	const { email, cookie, story } = await seed();
	await waitForIndex(story.id, cookie);
	const browser = await chromium.launch();
	const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
	const errors = [];
	page.on("pageerror", (error) => errors.push(String(error)));
	page.on("console", (message) => { if (message.type() === "error" && !/Failed to load resource|favicon/.test(message.text())) errors.push(message.text()); });

	await page.goto(`${WEB}/login`);
	await page.fill('input[type="email"]', email);
	await page.fill('input[type="password"]', PASSWORD);
	await page.getByRole("button", { name: "Sign in" }).click();
	await page.waitForURL(/dashboard/, { timeout: 20_000 });
	await page.goto(`${WEB}/stories/${story.id}`);
	await page.waitForSelector(".manuscript-editor", { timeout: 20_000 });

	await page.locator('.desk-toggle').click();
	await page.getByRole('tab', { name: 'Find', exact: true }).click();
	const search = page.getByLabel("Search this story");
	await search.waitFor({ state: "visible" });
	check("find-in-story panel opens", await search.isVisible());
	check("find tab is active", await page.getByRole("tab", { name: "Find", exact: true }).getAttribute("aria-selected") === "true");

	await search.fill("lantern");
	await page.waitForSelector(".search-card", { timeout: 30_000 });
	const cardCount = await page.locator(".search-card").count();
	check("query returns passages", cardCount >= 2, `${cardCount} cards`);
	const firstQuote = await page.locator(".search-quote").first().innerText();
	check("result quotes the manuscript", /lantern/i.test(firstQuote), firstQuote.slice(0, 80));
	const meta = await page.locator(".search-card-head").first().innerText();
	check("result shows chapter and lines", /Chapter \d/.test(meta) && /lines \d/.test(meta), meta.replace(/\n/g, " / "));

	await page.locator(".search-why summary").first().click();
	const breakdown = await page.locator(".search-why dl").first().innerText();
	check("score breakdown is visible", (await page.locator(".search-why dl").first().isVisible()) && /Merged score/.test(breakdown), breakdown.replace(/\n/g, " / "));
	check("breakdown names the retrieval paths", /Vector/.test(breakdown) || /Full text/.test(breakdown));

	const fromChapter = page.locator(".story-search-filters label", { hasText: "From chapter" }).locator("input");
	await fromChapter.fill("2");
	await page.waitForResponse((response) => response.url().includes(`/stories/${story.id}/search`) && response.url().includes("chapter_min=2"), { timeout: 15_000 });
	await page.waitForTimeout(150);
	const numbers = await page.locator(".search-card-head strong").allInnerTexts();
	check("chapter filter applies", numbers.length > 0 && numbers.every((text) => Number(text.match(/\d+/)?.[0]) >= 2), numbers.join(", "));

	await page.locator(".search-open").first().click();
	await page.waitForTimeout(500);
	const caret = await page.evaluate(() => {
		const editor = document.querySelector(".manuscript-editor");
		if (!(editor instanceof HTMLTextAreaElement)) return { focused: false, text: "" };
		return { focused: document.activeElement === editor, text: editor.value.slice(editor.selectionStart, editor.selectionEnd) };
	});
	check("open in chapter focuses the editor", caret.focused);
	check("open in chapter selects the hit line", /lantern/i.test(caret.text), caret.text.slice(0, 80));
	check("desk closes after opening the chapter", await page.locator(".insights-pane").count() === 0);
	check("no browser console errors", errors.length === 0, errors.join(" | ").slice(0, 240));

	await browser.close();
	const failed = results.filter((item) => !item.ok);
	console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
	process.exit(failed.length ? 1 : 0);
}

main().catch((error) => { console.error(error); process.exit(1); });
