import { chromium } from "playwright";
const WEB = "http://127.0.0.1:3000", API = "http://127.0.0.1:8000";
const stamp = Date.now(), email = `shot${stamp}@example.com`, PASSWORD = "correct horse battery";
async function request(path, options = {}, cookie) {
	const response = await fetch(`${API}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(cookie ? { Cookie: cookie } : {}), ...options.headers } });
	const text = await response.text();
	if (!response.ok) throw new Error(`${path} -> ${response.status} ${text}`);
	return text ? JSON.parse(text) : null;
}
await request("/register", { method: "POST", body: JSON.stringify({ username: `shot${stamp}`, email, password: PASSWORD }) });
const r = await fetch(`${API}/token`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const cookie = (r.headers.get("set-cookie") ?? "").split(";")[0];
const story = await request("/stories", { method: "POST", body: JSON.stringify({ title: "The Lantern Road" }) }, cookie);
const c1 = await request(`/stories/${story.id}/chapters`, { method: "POST", body: JSON.stringify({ title: "The Gate", content: "Mira Voss crossed the yard before dawn.\nHollis carried a lantern, and said nothing." }) }, cookie);
await request(`/stories/${story.id}/chapters`, { method: "POST", body: JSON.stringify({ title: "Night Watch", content: "Sable waited for the watch.\nNobody came." }) }, cookie);
const arc = await request(`/stories/${story.id}/arcs`, { method: "POST", body: JSON.stringify({ name: "The long winter" }) }, cookie);
await request(`/stories/${story.id}/arcs`, { method: "PUT", body: JSON.stringify({ arc_id: arc.id, chapter_ids: [c1.id] }) }, cookie);
for (const [name, type] of [["Mira Voss", "character"], ["Hollis", "character"], ["Sable", "character"], ["The Gate", "location"]]) {
	const e = await request(`/stories/${story.id}/entities`, { method: "POST", body: JSON.stringify({ name, entity_type: type, summary: name === "Mira Voss" ? "Gatekeeper of the north yard." : "" }) }, cookie);
	if (name === "Mira Voss") {
		for (const [value, confidence] of [["grey", 92], ["green", 71]]) {
			await request(`/entities/${e.id}/facts`, { method: "POST", body: JSON.stringify({ predicate: "eye colour", value_text: value, chapter_id: c1.id, quote: "Mira Voss crossed the yard before dawn.", status: "proposed", confidence }) }, cookie);
		}
	}
}
await request(`/stories/${story.id}/threads`, { method: "POST", body: JSON.stringify({ title: "Who lit the lantern?", description: "Hollis never says who lit it.", setup_chapter_id: c1.id, setup_quote: "Hollis carried a lantern" }) }, cookie);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await page.goto(`${WEB}/login`);
await page.fill('input[type="email"]', email);
await page.fill('input[type="password"]', PASSWORD);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL(/dashboard/);
const tmp = "C:/Users/ACER/AppData/Local/Temp";
await page.goto(`${WEB}/stories/${story.id}/wiki`);
await page.waitForSelector(".wiki-row-main");
await page.screenshot({ path: `${tmp}/p4-wiki.png` });
await page.goto(`${WEB}/stories/${story.id}/wiki/review`);
await page.waitForSelector(".inbox-item");
await page.getByRole("button", { name: "Auto-accept rules" }).click();
await page.waitForTimeout(800);
await page.screenshot({ path: `${tmp}/p4-inbox.png` });
await page.goto(`${WEB}/stories/${story.id}/wiki/threads`);
await page.waitForSelector(".thread-card");
await page.screenshot({ path: `${tmp}/p4-threads.png` });
await page.goto(`${WEB}/stories/${story.id}?chapter=${c1.id}`);
await page.waitForSelector(".manuscript-editor");
await page.keyboard.press("Control+k");
await page.waitForSelector(".command-dialog");
await page.locator(".command-input").fill("Mira");
await page.waitForTimeout(900);
await page.screenshot({ path: `${tmp}/p4-palette.png` });
await page.keyboard.press("Escape");
await page.getByRole("tab", { name: /Mentions/ }).click();
await page.waitForTimeout(600);
await page.screenshot({ path: `${tmp}/p4-desk.png` });
await browser.close();
console.log("ok");
