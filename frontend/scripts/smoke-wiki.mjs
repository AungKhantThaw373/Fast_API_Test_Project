// Temporary smoke check for the wiki route against a running stack.
import { chromium } from "playwright";

const WEB = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000";
const stamp = Date.now();

async function api(path, options = {}, cookie) {
	const response = await fetch(`${API}${path}`, {
		...options,
		headers: {
			"Content-Type": "application/json",
			...(cookie ? { Cookie: cookie } : {}),
			...options.headers,
		},
	});
	const text = await response.text();
	if (!response.ok) throw new Error(`${options.method ?? "GET"} ${path} -> ${response.status} ${text}`);
	return text ? JSON.parse(text) : null;
}

async function main() {
	const email = `smoke${stamp}@example.com`;
	const user = await api("/register", {
		method: "POST",
		body: JSON.stringify({ username: `smoke${stamp}`, email, password: "correct horse battery" }),
	});
	const form = new URLSearchParams({ username: email, password: "correct horse battery" });
	const tokenResponse = await fetch(`${API}/token`, {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: form,
	});
	const cookie = (tokenResponse.headers.get("set-cookie") ?? "").split(";")[0];
	if (!cookie) throw new Error("no session cookie from /token");
	const story = await api("/stories", { method: "POST", body: JSON.stringify({ title: `Smoke ${stamp}` }) }, cookie);
	const chapter = await api(`/stories/${story.id}/chapters`, {
		method: "POST",
		body: JSON.stringify({ title: "One", content: "Mira Voss crossed the yard.\nThe captain watched." }),
	}, cookie);
	for (const [name, type] of [["Mira Voss", "character"], ["Jax", "character"], ["The Yard", "location"]]) {
		const entity = await api(`/stories/${story.id}/entities`, {
			method: "POST",
			body: JSON.stringify({ name, entity_type: type, summary: `${name} summary.` }),
		}, cookie);
		await api(`/entities/${entity.id}/facts`, {
			method: "POST",
			body: JSON.stringify({ predicate: "summary", value_text: `${name} fact.`, chapter_id: chapter.id, quote: "Mira Voss crossed the yard." }),
		}, cookie);
	}

	const browser = await chromium.launch();
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
	const errors = [];
	page.on("pageerror", (error) => errors.push(String(error)));
	page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });

	await page.goto(`${WEB}/login`);
	await page.fill('input[type="email"]', email);
	await page.fill('input[type="password"]', "correct horse battery");
	await page.getByRole("button", { name: "Sign in" }).click();
	await page.waitForURL(/dashboard/, { timeout: 15000 });

	await page.goto(`${WEB}/stories/${story.id}/wiki`);
	await page.waitForSelector(".wiki-row-main", { timeout: 15000 });
	const rows = await page.locator(".wiki-row-main").count();
	console.log("rows:", rows);
	console.log("names:", await page.locator(".wiki-row-head strong").allInnerTexts());
	await page.screenshot({ path: "C:/Users/ACER/AppData/Local/Temp/wiki-list.png", fullPage: true });

	await page.keyboard.press("j");
	await page.keyboard.press("Enter");
	await page.waitForURL(/\/wiki\/[0-9a-f-]{36}$/, { timeout: 15000 });
	await page.waitForSelector(".wiki-detail-title h1", { timeout: 15000 });
	console.log("opened:", page.url());
	await page.screenshot({ path: "C:/Users/ACER/AppData/Local/Temp/wiki-detail.png", fullPage: true });

	// The provenance chip must land in the studio with the cited line selected.
	await page.locator(".provenance-chip").first().click();
	await page.waitForURL(/\/stories\/[0-9a-f-]+\?chapter=/, { timeout: 15000 });
	await page.waitForSelector(".manuscript-editor", { timeout: 15000 });
	const selection = await page.evaluate(() => {
		const editor = document.querySelector(".manuscript-editor");
		return editor ? editor.value.slice(editor.selectionStart, editor.selectionEnd) : "";
	});
	console.log("selected line:", JSON.stringify(selection));
	await page.screenshot({ path: "C:/Users/ACER/AppData/Local/Temp/wiki-deeplink.png", fullPage: false });

	console.log("errors:", errors.slice(0, 5));
	await browser.close();
	if (rows !== 3) throw new Error(`expected 3 rows, saw ${rows}`);
	if (errors.length) throw new Error("console errors: " + errors.join(" | "));
	console.log("SMOKE OK", user.username);
}

main().catch((error) => {
	console.error("SMOKE FAILED", error);
	process.exit(1);
});
