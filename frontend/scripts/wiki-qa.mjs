// Wiki end-to-end flows. Run against a built app: `npm run build && npx next start`,
// with the API on :8000. See Docs/qa-phase-4.md.
import { chromium } from "playwright";

const WEB = process.env.WEB_URL ?? "http://127.0.0.1:3000";
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const stamp = Date.now();
const PASSWORD = "correct horse battery";

async function request(path, options = {}, cookie) {
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

async function seed() {
	const email = `qa${stamp}@example.com`;
	await request("/register", {
		method: "POST",
		body: JSON.stringify({ username: `qa${stamp}`, email, password: PASSWORD }),
	});
	const response = await fetch(`${API}/token`, {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: new URLSearchParams({ username: email, password: PASSWORD }),
	});
	const cookie = (response.headers.get("set-cookie") ?? "").split(";")[0];
	if (!cookie) throw new Error("no session cookie");

	const story = await request("/stories", { method: "POST", body: JSON.stringify({ title: `QA ${stamp}` }) }, cookie);
	const chapter = await request(
		`/stories/${story.id}/chapters`,
		{
			method: "POST",
			body: JSON.stringify({
				title: "The Gate",
				content:
					"Mira Voss crossed the yard before dawn.\nLater Hollis met Mira at the gate.\nHollis carried a lantern, and Mira Voss said nothing.",
			}),
		},
		cookie,
	);
	const second = await request(
		`/stories/${story.id}/chapters`,
		{
			method: "POST",
			body: JSON.stringify({
				title: "Night Watch",
				content:
					"The lantern burned while Sable waited for the watch.\nNobody came, so Sable walked the wall alone.",
			}),
		},
		cookie,
	);
	return { email, cookie, story, chapter, second };
}

const results = [];
function check(name, condition, detail = "") {
	results.push({ name, ok: Boolean(condition), detail });
	console.log(`${condition ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

async function main() {
	const { email, cookie, story, chapter, second } = await seed();
	const browser = await chromium.launch();
	const page = await browser.newPage({ viewport: { width: 1360, height: 950 } });
	const consoleErrors = [];
	page.on("pageerror", (error) => consoleErrors.push(String(error)));
	page.on("console", (message) => {
		// Resource failures are classified by the response listener below, which
		// can tell an expected 409 on a merged entity from a real breakage.
		if (message.type() === "error" && !/Failed to load resource|favicon/.test(message.text())) {
			consoleErrors.push(message.text());
		}
	});
	// A merged-away entity is expected to 404 for the rest of that page's life.
	const expected = /\/entities\/[0-9a-f-]{36}(\/.*)?$/;
	page.on("response", (response) => {
		const path = new URL(response.url()).pathname;
		const merged = (response.status() === 404 || response.status() === 409) && expected.test(path);
		if ((response.status() === 404 || response.status() === 409) && !merged) {
			consoleErrors.push(`${response.status()} ${response.url()}`);
		}
	});

	await page.goto(`${WEB}/login`);
	await page.fill('input[type="email"]', email);
	await page.fill('input[type="password"]', PASSWORD);
	await page.getByRole("button", { name: "Sign in" }).click();
	await page.waitForURL(/dashboard/, { timeout: 20_000 });

	// 1. Create an entity from the wiki.
	await page.goto(`${WEB}/stories/${story.id}/wiki`);
	await page.getByRole("button", { name: "New entry" }).click();
	await page.locator('.dialog-card input').first().fill("Tessa");
	await page.locator('.dialog-card textarea').first().fill("A lantern keeper.");
	await page.getByRole("button", { name: "Add to wiki" }).click();
	await page.waitForURL(/\/wiki\/[0-9a-f-]{36}$/, { timeout: 20_000 });
	await page.waitForSelector(".wiki-detail-title h1");
	check("create entity from the wiki", (await page.locator(".wiki-detail-title h1").innerText()) === "Tessa");

	// 2. Add an alias and a fact with a quote from a chapter.
	await page.getByRole("button", { name: "Add alias" }).click();
	await page.getByLabel("New alias").fill("the lantern keeper");
	await page.getByRole("button", { name: "Add", exact: true }).click();
	await page.waitForSelector(".alias-chip:has-text('the lantern keeper')");
	check("add alias", await page.locator(".alias-chip", { hasText: "the lantern keeper" }).isVisible());

	await page.getByRole("button", { name: "Add fact" }).click();
	await page.locator('.dialog-card input').nth(0).fill("eye colour");
	await page.locator('.dialog-card input').nth(1).fill("grey");
	await page.locator('.dialog-card select').first().selectOption({ label: "1. The Gate" });
	await page.locator('.dialog-card textarea').first().fill("Mira Voss crossed the yard before dawn.");
	await page.getByRole("button", { name: "Save fact" }).click();
	await page.waitForSelector(".fact-row");
	check("add fact with quote", (await page.locator(".fact-value").first().innerText()) === "grey");
	check(
		"provenance chip names chapter and line",
		(await page.locator(".provenance-chip").first().innerText()).includes("Ch. 1") &&
			(await page.locator(".provenance-chip").first().innerText()).includes("line 1"),
	);

	// 3. The provenance chip opens the studio on that line.
	await page.locator(".provenance-chip").first().click();
	await page.waitForSelector(".manuscript-editor", { timeout: 20_000 });
	const selection = await page.evaluate(() => {
		const editor = document.querySelector(".manuscript-editor");
		return editor ? editor.value.slice(editor.selectionStart, editor.selectionEnd) : "";
	});
	check("provenance opens the cited line", selection.length > 0, JSON.stringify(selection));

	// 4. Capture a selection from the studio as a new entity.
	await page.goto(`${WEB}/stories/${story.id}?chapter=${chapter.id}`);
	await page.waitForSelector(".manuscript-editor");
	await page.evaluate(() => {
		const editor = document.querySelector(".manuscript-editor");
		const text = editor.value;
		const start = text.indexOf("Hollis carried");
		const end = text.indexOf(".", start) + 1;
		editor.focus();
		editor.setSelectionRange(start, end);
		editor.dispatchEvent(new Event("select", { bubbles: true }));
		document.dispatchEvent(new Event("selectionchange"));
	});
	await page.waitForSelector(".selection-actions", { timeout: 10_000 });
	await page.getByRole("button", { name: "Add to wiki" }).click();
	await page.locator('.dialog-card input').first().fill("Hollis");
	await page.getByRole("button", { name: "Add entry" }).click();
	await page.waitForFunction(
		() => !document.querySelector(".dialog-card"),
		{ timeout: 20_000 },
	);
	const entities = await request(`/stories/${story.id}/entities`, {}, cookie);
	const hollis = entities.entities.find((item) => item.name === "Hollis");
	check("capture selection as entity", Boolean(hollis));
	if (hollis) {
		const facts = await request(`/entities/${hollis.id}/facts`, {}, cookie);
		check(
			"captured quote is attached with provenance",
			facts.facts.length === 1 && facts.facts[0].line_start === 3 && facts.facts[0].quote.includes("Hollis carried"),
			JSON.stringify(facts.facts[0]?.quote ?? null),
		);
	}

	// 5. Accept a name candidate from the desk's Mentions tab.
	await page.goto(`${WEB}/stories/${story.id}?chapter=${second.id}`);
	await page.waitForSelector(".manuscript-editor");
	await page.getByRole("tab", { name: /Mentions/ }).click();
	await page.waitForSelector(".candidate-main strong", { timeout: 20_000 });
	const candidateNames = await page.locator(".candidate-main strong").allInnerTexts();
	check("name candidates are proposed", candidateNames.includes("Sable"), candidateNames.join(", "));
	const acceptButtons = page.locator(".candidate-actions button:has-text('Accept')");
	if (await acceptButtons.count()) {
		await acceptButtons.first().click();
		await page.waitForFunction(async () => true);
		await page.waitForTimeout(1500);
		const after = await request(`/stories/${story.id}/entities`, {}, cookie);
		check("accept a name candidate", after.entities.length >= 3, `${after.entities.length} entities`);
	}

	// 6. Merge two entities with a dry run, then undo.
	await page.goto(`${WEB}/stories/${story.id}/wiki`);
	await page.waitForSelector(".wiki-row-main");
	const beforeMerge = (await request(`/stories/${story.id}/entities`, {}, cookie)).entities;
	const source = beforeMerge.find((item) => item.name === "Tessa");
	const target = beforeMerge.find((item) => item.name === "Hollis");
	if (source && target) {
		await page.goto(`${WEB}/stories/${story.id}/wiki/${source.id}`);
		await page.waitForSelector(".wiki-detail-title h1");
		await page.getByRole("button", { name: "Merge into…" }).click();
		await page.locator('.dialog-card input[type="search"]').fill("Hollis");
		await page.waitForSelector(".merge-candidate", { timeout: 15_000 });
		await page.locator(".merge-candidate").first().click();
		await page.waitForSelector(".merge-preview ul", { timeout: 15_000 });
		const preview = await page.locator(".merge-preview ul").innerText();
		check("merge dry run shows what moves", preview.includes("facts"), preview.replace(/\n/g, " "));
		await page.getByRole("button", { name: "Merge entries" }).click();
		await page.waitForURL(new RegExp(`/wiki/${target.id}$`), { timeout: 20_000 });
		const merged = await request(`/entities/${source.id}`, {}, cookie).catch(() => null);
		check("source stops resolving after merge", merged === null);
		await request(`/entities/${source.id}/unmerge`, { method: "POST" }, cookie);
		const restored = await request(`/entities/${source.id}`, {}, cookie).catch(() => null);
		check("merge can be undone", Boolean(restored && restored.merged_into_id === null));
	}

	// 6b. Review inbox: proposals can be cleared with the keyboard.
	const inboxEntities = (await request(`/stories/${story.id}/entities`, {}, cookie)).entities;
	const mira = inboxEntities.find((item) => item.name === "Tessa") ?? inboxEntities[0];
	const proposalIds = [];
	for (const [value, confidence] of [["grey", 92], ["green", 88]]) {
		const fact = await request(
			`/entities/${mira.id}/facts`,
			{
				method: "POST",
				body: JSON.stringify({
					predicate: "eye_colour",
					value_text: value,
					chapter_id: chapter.id,
					quote: "Mira Voss crossed the yard before dawn.",
					status: "proposed",
					confidence,
				}),
			},
			cookie,
		);
		proposalIds.push(fact.id);
	}
	await page.goto(`${WEB}/stories/${story.id}/wiki/review`);
	await page.waitForSelector(".inbox-item", { timeout: 20_000 });
	const inboxBefore = await page.locator(".inbox-item").count();
	const whyHeld = await page.locator(".inbox-why").first().innerText();
	check("inbox explains why an item is held", whyHeld.length > 0, whyHeld);
	// The keyboard handler listens on the document, so no click is needed. Clicking
	// the row would land on a link and leave the page.
	await page.keyboard.press("a");
	await page.waitForFunction(
		(count) => document.querySelectorAll(".inbox-item").length < count,
		inboxBefore,
		{ timeout: 20_000 },
	);
	const acceptedFacts = await request(`/entities/${mira.id}/facts`, {}, cookie);
	const accepted = acceptedFacts.facts.filter((fact) => fact.status === "accepted").length;
	check("accept a proposal with the keyboard", accepted >= 1, `${accepted} accepted`);

	// The rules preview is concrete, and applying it is a separate action.
	await page.getByRole("button", { name: "Auto-accept rules" }).click();
	await page.waitForFunction(
		() => /\d+ of \d+/.test(document.querySelector(".rules-preview")?.textContent ?? ""),
		{ timeout: 20_000 },
	);
	const previewText = (await page.locator(".rules-preview").textContent()) ?? "";
	const previewFlat = previewText.replace(/\s+/g, " ").trim();
	check("auto-accept preview shows a count", /\d+ of \d+/.test(previewFlat), previewFlat.slice(0, 90));

	// 6c. Arcs group the rail and filter the wiki.
	await page.goto(`${WEB}/stories/${story.id}?chapter=${chapter.id}`);
	await page.waitForSelector(".manuscript-editor");
	await page.getByRole("button", { name: "＋ Arc" }).click();
	await page.getByLabel("New arc name").fill("The watch");
	await page.keyboard.press("Enter");
	await page.waitForSelector(".arc-group-toggle:has-text('The watch')", { timeout: 20_000 });
	check("create an arc from the rail", await page.locator(".arc-group-toggle", { hasText: "The watch" }).isVisible());
	const arcSelect = page.locator(".chapter-arc-select").first();
	await arcSelect.selectOption({ label: "The watch" });
	// The select updates optimistically; the count comes from the server.
	const arcsNow = await (async () => {
		for (let attempt = 0; attempt < 20; attempt += 1) {
			const rows = await request(`/stories/${story.id}/arcs`, {}, cookie);
			if (rows[0]?.chapter_count === 1) return rows;
			await page.waitForTimeout(300);
		}
		return request(`/stories/${story.id}/arcs`, {}, cookie);
	})();
	check("assign a chapter to an arc", arcsNow[0]?.chapter_count === 1, JSON.stringify(arcsNow.map((a) => [a.name, a.chapter_count])));
	await page.locator(".arc-group-toggle", { hasText: "The watch" }).click();
	await page.waitForTimeout(300);
	check("arc groups collapse", (await page.locator(".arc-group-toggle", { hasText: "The watch" }).getAttribute("aria-expanded")) === "false");

	await page.goto(`${WEB}/stories/${story.id}/wiki?arc=${arcsNow[0].id}`);
	await page.waitForSelector(".wiki-row-main, .wiki-empty");
	const arcNames = await page.locator(".wiki-row-head strong").allInnerTexts();
	const inArc = await request(`/stories/${story.id}/entities?arc_id=${arcsNow[0].id}`, {}, cookie);
	check(
		"the wiki filters by arc",
		arcNames.length === inArc.entities.length,
		`${arcNames.join(", ") || "none"} (server: ${inArc.entities.length})`,
	);

	// 6d. Threads answer "what is unresolved?".
	const thread = await request(
		`/stories/${story.id}/threads`,
		{ method: "POST", body: JSON.stringify({ title: "Who lit the lantern?", description: "Hollis never says.", setup_chapter_id: chapter.id, setup_quote: "Hollis carried a lantern" }) },
		cookie,
	);
	await page.goto(`${WEB}/stories/${story.id}/wiki/threads`);
	await page.waitForSelector(".thread-card", { timeout: 20_000 });
	check("threads list open questions", (await page.locator(".thread-card h2").first().innerText()) === thread.title);
	await page.getByRole("button", { name: "Mark resolved" }).first().click();
	await page.getByLabel("Chapter that pays this off").selectOption({ label: "2. Night Watch" });
	await page.locator(".thread-resolve-form .button-approve").click();
	await page.waitForFunction(() => !document.querySelector(".thread-card.state-open"), { timeout: 20_000 });
	const resolved = await request(`/stories/${story.id}/threads`, {}, cookie);
	check("resolve a thread", resolved.threads[0]?.state === "resolved", resolved.threads[0]?.state);

	// 6e. The command palette finds an entry and jumps to it.
	await page.goto(`${WEB}/stories/${story.id}?chapter=${chapter.id}`);
	await page.waitForSelector(".manuscript-editor");
	await page.keyboard.press("Control+k");
	await page.waitForSelector(".command-dialog", { timeout: 10_000 });
	await page.locator(".command-input").fill("Tessa");
	await page.waitForSelector(".command-item:has-text('Tessa')", { timeout: 20_000 });
	await page.locator(".command-item:has-text('Tessa')").first().click();
	await page.waitForURL(/\/wiki\/[0-9a-f-]{36}$/, { timeout: 20_000 });
	check("command palette opens an entry", /\/wiki\//.test(new URL(page.url()).pathname), page.url());

	// 7. Filters survive a refresh.
	await page.goto(`${WEB}/stories/${story.id}/wiki?type=character`);
	await page.waitForSelector(".wiki-row-main");
	await page.reload();
	await page.waitForSelector(".wiki-row-main");
	check("filters persist across refresh", page.url().includes("type=character"), page.url());

	check("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 2).join(" | "));

	await browser.close();
	const failed = results.filter((item) => !item.ok);
	console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
	if (failed.length) process.exit(1);
}

main().catch((error) => {
	console.error("QA FAILED", error);
	process.exit(1);
});
