import { chromium } from "playwright";

const WEB = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000";
const stamp = Date.now();
const PASSWORD = "correct horse battery";

async function request(path, options = {}, cookie) {
	const response = await fetch(API + path, {
		...options,
		headers: { "Content-Type": "application/json", ...(cookie ? { Cookie: cookie } : {}), ...options.headers },
	});
	const text = await response.text();
	if (!response.ok) throw new Error(options.method + " " + path + " -> " + response.status + " " + text);
	return text ? JSON.parse(text) : null;
}

const email = "p6qa" + stamp + "@example.com";
await request("/register", { method: "POST", body: JSON.stringify({ username: "p6qa" + stamp, email, password: PASSWORD }) });
const token = await fetch(API + "/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const rawCookie = (token.headers.get("set-cookie") || "").split(";")[0];
if (!rawCookie) throw new Error("no cookie");
await request("/ai-settings", { method: "PUT", body: JSON.stringify({ provider: "ollama", model: "qwen3:4b-instruct", api_key: null, base_url: "http://127.0.0.1:11434" }) }, rawCookie);
const story = await request("/stories", { method: "POST", body: JSON.stringify({ title: "Phase 6 QA " + stamp }) }, rawCookie);
await request("/stories/" + story.id, { method: "PATCH", body: JSON.stringify({ external_analysis_enabled: true, scan_interval_words: 2000 }) }, rawCookie);
const first = await request("/stories/" + story.id + "/chapters", { method: "POST", body: JSON.stringify({ title: "The Gate", content: "Mira Voss crossed the yard at dawn. Her eyes were blue. She carried a brass lantern." }) }, rawCookie);
const second = await request("/stories/" + story.id + "/chapters", { method: "POST", body: JSON.stringify({ title: "Night Watch", content: "Hollis waited at the gate after dusk. The brass lantern was still lit. Mira said she would return before moonrise." }) }, rawCookie);
for (const chapter of [first, second]) {
	for (let i = 0; i < 60; i += 1) {
		const status = await request("/stories/chapters/" + chapter.id + "/status", {}, rawCookie);
		if (status.index_status === "indexed") break;
		if (status.index_status === "failed") throw new Error("index failed: " + status.index_error);
		await new Promise((resolve) => setTimeout(resolve, 500));
	}
}

const results = [];
function check(name, condition, detail = "") {
	results.push({ name, ok: Boolean(condition), detail });
	console.log((condition ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1360, height: 950 } });
const errors = [];
page.on("pageerror", (error) => errors.push(String(error)));
const [name, value] = rawCookie.split("=");
await page.context().addCookies([{ name, value, domain: "127.0.0.1", path: "/" }]);
await page.goto(WEB + "/stories/" + story.id);
await page.getByText("AI usage this month").waitFor({ timeout: 20000 });
check("usage panel is visible", await page.getByText("AI usage this month").isVisible());

await page.getByRole("tab", { name: "Find", exact: true }).click();
await page.getByLabel("Ask a question about this story").fill("What colour were Mira's eyes?");
await page.getByRole("button", { name: "Ask", exact: true }).click();
await page.locator(".story-ask-result").waitFor({ timeout: 120000 });
const answer = (await page.locator(".story-ask-result p").innerText()).trim();
check("ask returns an answer", answer.length > 0, answer);
const citationCount = await page.locator(".story-ask-result blockquote").count();
if (citationCount > 0) {
	const citation = await page.locator(".story-ask-result blockquote").first().innerText();
	check("ask shows a citation", /blue/i.test(citation), citation);
} else {
	console.log("INFO ask reflected model uncertainty without a citation in this run");
}

await page.keyboard.press("Control+k");
const paletteAsk = page.getByRole("option").filter({ hasText: "Ask your story" });
await paletteAsk.waitFor({ timeout: 10000 });
await paletteAsk.click();
await page.getByLabel("Ask a question about this story").waitFor({ timeout: 10000 });
const askFocused = await page.getByLabel("Ask a question about this story").evaluate((element) => element === document.activeElement);
check("command palette focuses Ask", askFocused);

await page.locator(".chapter-nav-item", { hasText: "Night Watch" }).click();
await page.getByRole("tab", { name: /Findings/ }).click();
await page.getByRole("button", { name: "Check draft" }).click();
await page.getByText(/Checking/).first().waitFor({ timeout: 30000 });
await page.waitForFunction(() => {
	for (let index = 0; index < window.sessionStorage.length; index += 1) {
		const key = window.sessionStorage.key(index);
		if (key && key.startsWith("stillroom-scan:")) return true;
	}
	return false;
}, null, { timeout: 120000 });
const keys = await page.evaluate(() => {
	const found = [];
	for (let index = 0; index < window.sessionStorage.length; index += 1) {
		const key = window.sessionStorage.key(index);
		if (key && key.startsWith("stillroom-scan:")) found.push(key);
	}
	return found;
});
check("scan job is tracked for reload", keys.length === 1, keys.join(","));
await page.reload();
await page.getByText(/Resuming the continuity check/).waitFor({ timeout: 20000 });
check("scan resumes after reload", true);
await page.getByText(/background check finished|scene.*could not be checked/i).first().waitFor({ timeout: 240000 });
const notice = await page.locator(".studio-notice").first().innerText();
check("scan completes after resume", /finished/i.test(notice), notice);
check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id, first: first.id, second: second.id }));
if (failed.length) process.exit(1);
