// Story-shaped wiki QA. Run against a production build with the API up.
import { chromium } from "playwright";

const WEB = process.env.WEB_URL ?? "http://127.0.0.1:3000";
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const EMAIL = "demo@stillroom.local";
const PASSWORD = "correct horse battery";
const stamp = Date.now();

function cookieHeader(response) {
	return (response.headers.getSetCookie?.() ?? [response.headers.get("set-cookie") ?? ""])
		.map((value) => value.split(";")[0])
		.filter(Boolean)
		.join("; ");
}

async function api(path, options = {}, session = "") {
	const response = await fetch(`${API}${path}`, {
		...options,
		headers: {
			"Content-Type": "application/json",
			...(session ? { Cookie: session } : {}),
			...options.headers,
		},
	});
	const text = await response.text();
	if (!response.ok) throw new Error(`${options.method ?? "GET"} ${path} -> ${response.status} ${text}`);
	return text ? JSON.parse(text) : null;
}

async function seed() {
	const health = await fetch(`${API}/health`);
	const csrfCookie = (health.headers.getSetCookie?.() ?? [])
		.map((value) => value.split(";")[0])
		.find((value) => value.startsWith("csrf="));
	if (!csrfCookie) throw new Error("no csrf cookie");
	const csrf = csrfCookie.slice("csrf=".length);
	const login = await fetch(`${API}/token`, {
		method: "POST",
		headers: {
			"Content-Type": "application/x-www-form-urlencoded",
			"X-CSRF-Token": csrf,
			Cookie: csrfCookie,
		},
		body: new URLSearchParams({ username: EMAIL, password: PASSWORD }),
	});
	if (!login.ok) throw new Error(`login -> ${login.status} ${await login.text()}`);
	const session = cookieHeader(login);
	if (!session) throw new Error("no session cookie");
	const headers = { "X-CSRF-Token": csrf, Cookie: `${csrfCookie}; ${session}` };
	const story = await api("/stories", { method: "POST", body: JSON.stringify({ title: `QA wiki format ${stamp}` }), headers }, session);
	return { story, headers };
}

function assert(condition, message) {
	if (!condition) throw new Error(message);
	console.log(`PASS ${message}`);
}

async function main() {
	const { story, headers } = await seed();
	const browser = await chromium.launch();
	const page = await browser.newPage({ viewport: { width: 1360, height: 950 } });
	const errors = [];
	page.on("pageerror", (error) => errors.push(String(error)));
	page.on("console", (message) => {
		if (message.type() === "error" && !/Failed to load resource|favicon/.test(message.text())) errors.push(message.text());
	});
	try {
		await page.goto(`${WEB}/login`);
		await page.fill('input[type="email"]', EMAIL);
		await page.fill('input[type="password"]', PASSWORD);
		await page.getByRole("button", { name: "Sign in" }).click();
		await page.waitForURL(/dashboard/, { timeout: 20_000 });

		await page.goto(`${WEB}/stories/${story.id}/wiki`);
		await page.getByRole("button", { name: "Format", exact: true }).click();
		await page.getByRole("heading", { name: "Shape this wiki" }).waitFor();
		const initialTypes = await page.locator(".wiki-format-type").count();
		assert(initialTypes >= 9, "default format lists the starting types");

		await page.getByRole("button", { name: "+ Add an entry type" }).click();
		const typeCard = page.locator(".wiki-format-type").last();
		await typeCard.getByLabel(/Name for entry type/).fill("Technique");
		await typeCard.locator("label.wiki-format-description input").fill("A named move with a cost.");
		assert((await typeCard.locator(".wiki-format-key").innerText()) === "technique", "new type key follows its name");
		await typeCard.getByRole("checkbox", { name: "Relationships" }).uncheck();
		await typeCard.getByRole("checkbox", { name: "Aliases" }).uncheck();
		await typeCard.getByRole("button", { name: "Add field" }).click();
		await typeCard.getByLabel("Field 1 label").fill("Element");
		assert((await typeCard.getByLabel("Field 1 stored key").inputValue()) === "element", "new field key follows its label");
		await page.getByRole("button", { name: "Save format" }).click();
		await page.locator(".wiki-format-dialog").waitFor({ state: "detached" });
		console.log("PASS save a custom type, sections, and field");

		await page.getByRole("button", { name: "New entry" }).click();
		const add = page.getByRole("dialog");
		await add.getByLabel("Name", { exact: true }).fill("Flame Step");
		await add.getByLabel(/^Type/).fill("technique");
		await add.getByLabel("Summary", { exact: true }).fill("A movement technique.");
		await add.getByRole("button", { name: "Add to wiki" }).click();
		await page.waitForURL(/\/wiki\/[0-9a-f-]{36}$/, { timeout: 20_000 });
		await page.getByRole("heading", { name: "Flame Step" }).waitFor();
		assert(await page.locator(".wiki-type-chip", { hasText: "Technique" }).isVisible(), "entry uses the configured type label");
		assert((await page.locator('section[aria-labelledby="aliases-heading"]').count()) === 0, "disabled aliases section is hidden");
		assert((await page.locator('section[aria-labelledby="relationships-heading"]').count()) === 0, "disabled relationships section is hidden");

		const fields = page.locator(".wiki-fields-section");
		assert(await fields.isVisible(), "entry shows its configured field");
		await fields.getByRole("button", { name: "Add", exact: true }).click();
		await fields.getByLabel("Element", { exact: true }).fill("fire");
		await fields.getByRole("button", { name: "Save", exact: true }).click();
		await fields.getByText("fire", { exact: true }).waitFor();
		assert((await fields.locator(".provenance-chip").innerText()).includes("No source"), "manual field carries a no-source provenance chip");
		const facts = page.locator('section[aria-labelledby="facts-heading"]');
		assert((await facts.getByText("Element", { exact: true }).count()) === 0, "configured field is not duplicated in Facts");

		await fields.getByRole("button", { name: "Edit" }).click();
		await fields.getByLabel("Element", { exact: true }).fill("ash");
		await fields.getByRole("button", { name: "Save", exact: true }).click();
		await fields.getByText("ash", { exact: true }).waitFor();
		console.log("PASS edit a manual field without a chapter");

		await page.getByRole("button", { name: "Format", exact: true }).click();
		await page.getByRole("button", { name: "Restore default" }).click();
		const alert = page.getByRole("alertdialog");
		await alert.getByRole("button", { name: "Restore default" }).click();
		await page.getByText("Default wiki format restored.", { exact: true }).waitFor();
		await page.getByRole("button", { name: "Cancel" }).click();
		await page.locator(".wiki-fields-section").waitFor({ state: "detached" });
		assert(await page.locator('section[aria-labelledby="aliases-heading"]').isVisible(), "unknown type falls back to full sections");
		assert(await facts.getByText("Element", { exact: true }).isVisible(), "field fact survives removing the field definition");
		console.log("PASS reset restores the default without deleting entries or facts");

		await page.goto(`${WEB}/stories/${story.id}`);
		await page.locator(".studio-wiki-link").waitFor();
		assert((await page.locator(".studio-wiki-link").innerText()).includes("Full wiki"), "desk keeps one Full wiki control");
		assert(!(await page.locator(".mobile-file-menu").innerText()).includes("Open full story wiki"), "story menu no longer duplicates Full wiki");
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto(`${WEB}/stories/${story.id}/wiki`);
		await page.locator(".story-mobile-nav").waitFor();
		assert((await page.locator(".app-bottom-nav").count()) === 0, "mobile wiki uses the story nav, not a second global nav");
		assert(await page.locator(".story-mobile-nav").isVisible(), "mobile story nav stays visible");
		assert(!(await page.locator(".wiki-filters .wiki-select").first().isVisible()), "mobile filters start compact");
		await page.getByRole("button", { name: /^Filters/ }).click();
		assert(await page.locator(".wiki-filters .wiki-select").first().isVisible(), "mobile filters expand on request");
		await page.getByRole("button", { name: "Hide filters", exact: true }).click();
		const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
		assert(overflow <= 1, "mobile wiki has no horizontal overflow");
		assert(errors.length === 0, `no browser errors${errors.length ? `: ${errors.join(" | ")}` : ""}`);
	} finally {
		await browser.close();
		await api(`/stories/${story.id}`, { method: "DELETE", headers }, `${headers.Cookie}`).catch(() => undefined);
	}
}

main().catch((error) => {
	console.error(`FAIL ${error.message}`);
	process.exit(1);
});
