import { chromium } from "playwright";
import { apiHeaders, csrfToken } from "./qa-csrf.mjs";

const WEB = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000";
const stamp = Date.now();
const PASSWORD = "correct horse battery";
const csrf = await csrfToken(API);
const results = [];
function check(name, condition, detail = "") {
	results.push({ name, ok: Boolean(condition), detail });
	console.log((condition ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}
async function request(path, options = {}, cookie) {
	const response = await fetch(API + path, { ...options, headers: { ...apiHeaders(csrf, cookie), ...options.headers } });
	const text = await response.text();
	if (!response.ok) throw new Error((options.method || "GET") + " " + path + " -> " + response.status + " " + text);
	return text ? JSON.parse(text) : null;
}

const email = "canonqa" + stamp + "@example.com";
await request("/register", { method: "POST", body: JSON.stringify({ username: "canonqa" + stamp, email, password: PASSWORD }) });
const token = await fetch(API + "/token", { method: "POST", headers: { ...apiHeaders(csrf), "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const cookie = (token.headers.get("set-cookie") || "").split(";")[0];
if (!cookie) throw new Error("no auth cookie");
// Keep the drill on local Ollama so a cloud key in .env is not used as the
// fallback provider.
await request("/ai-settings", { method: "PUT", body: JSON.stringify({ provider: "ollama", model: "qwen3:4b-instruct", base_url: "http://127.0.0.1:11434" }) }, cookie);
const story = await request("/stories", { method: "POST", body: JSON.stringify({ title: "Canon coverage QA " + stamp }) }, cookie);
const chapters = [];
for (let number = 1; number <= 3; number += 1) {
	chapters.push(await request("/stories/" + story.id + "/chapters", { method: "POST", body: JSON.stringify({ title: "Chapter " + number, content: "Chapter " + number + " carries enough words to extract." }) }, cookie));
}
const early = await request("/stories/" + story.id + "/arcs", { method: "POST", body: JSON.stringify({ name: "The early arc" }) }, cookie);
const late = await request("/stories/" + story.id + "/arcs", { method: "POST", body: JSON.stringify({ name: "The late arc" }) }, cookie);
await request("/stories/" + story.id + "/arcs", { method: "PUT", body: JSON.stringify({ arc_id: early.id, chapter_ids: chapters.slice(0, 2).map((chapter) => chapter.id) }) }, cookie);
await request("/stories/" + story.id + "/arcs", { method: "PUT", body: JSON.stringify({ arc_id: late.id, chapter_ids: [chapters[2].id] }) }, cookie);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(String(error)));
await page.goto(WEB + "/login");
await page.getByLabel("Email").fill(email);
await page.getByLabel("Password").fill(PASSWORD);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL("**/dashboard", { timeout: 30000 });

await page.goto(WEB + "/stories/" + story.id + "/wiki/arcs/" + early.id);
await page.getByRole("heading", { name: "The early arc" }).waitFor({ timeout: 30000 });
const card = page.locator(".canon-card");
await card.waitFor({ timeout: 30000 });
await card.getByText("0 / 2", { exact: true }).waitFor({ timeout: 30000 });
const cardText = await card.innerText();
check("arc page shows canon coverage", cardText.includes("Canon extraction"));
check("coverage counts this arc", cardText.includes("0 / 2"), cardText.replace(/\n/g, " | "));
check("pending copy is honest", cardText.includes("2 chapters still to extract"));
check("rail shows current arc index", (await page.locator(".wiki-canon-summary").innerText()).includes("Arc 2 of 2"));

await card.getByRole("button", { name: "Extract remaining" }).click();
await page.getByText(/Queued 2 chapters/).waitFor({ timeout: 30000 });
check("backfill queues only this arc", true);
const coverage = await request("/stories/" + story.id + "/canon/coverage", {}, cookie);
check("coverage stays lazy after queue", coverage.arcs[0].pending_count === 2, JSON.stringify(coverage.arcs[0]));
check("page has no JS errors", errors.length === 0, errors.join("; "));
await page.screenshot({ path: "test-results/canon-coverage.png", fullPage: true });

await browser.close();
const failed = results.filter((result) => !result.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length }));
if (failed.length) process.exit(1);