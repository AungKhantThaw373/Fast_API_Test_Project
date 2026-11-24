// Phase 4 performance checks against a seeded story (see backend/scripts/seed_wiki.py).
//
//   cd backend && uv run python -m scripts.seed_wiki --email qa@example.com --title Perf --count 1000
//   cd frontend && node scripts/wiki-perf.mjs qa@example.com "correct horse battery" Perf
//
// It measures what the manual asks for: first render after data load, search,
// and entity detail, then prints a table with the targets.
import { chromium } from "playwright";

const WEB = process.env.WEB_URL ?? "http://127.0.0.1:3000";
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const [email, password, title = "Perf"] = process.argv.slice(2);

if (!email || !password) {
	console.error("usage: node scripts/wiki-perf.mjs <email> <password> [story title]");
	process.exit(2);
}

const token = await fetch(`${API}/token`, {
	method: "POST",
	headers: { "Content-Type": "application/x-www-form-urlencoded" },
	body: new URLSearchParams({ username: email, password }),
});
const cookie = (token.headers.get("set-cookie") ?? "").split(";")[0];
const stories = await (
	await fetch(`${API}/stories?limit=100`, { headers: { Cookie: cookie } })
).json();
const story = stories.stories.find((item) => item.title === title);
if (!story) throw new Error(`No story titled ${title}.`);
const entities = await (
	await fetch(`${API}/stories/${story.id}/entities?limit=5`, { headers: { Cookie: cookie } })
).json();
const sample = entities.entities[0];

const results = [];
const record = (name, ms, target) => results.push({ name, ms: Math.round(ms), target, ok: ms <= target });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } });
await page.goto(`${WEB}/login`);
await page.fill('input[type="email"]', email);
await page.fill('input[type="password"]', password);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL(/dashboard/);

// Search: time the round trip the UI makes, five times, and keep the median.
const searchTimings = [];
for (let attempt = 0; attempt < 5; attempt += 1) {
	const started = Date.now();
	const response = await fetch(
		`${API}/entities/search?story_id=${story.id}&q=${encodeURIComponent("Mira")}`,
		{ headers: { Cookie: cookie } },
	);
	await response.json();
	searchTimings.push(Date.now() - started);
}
searchTimings.sort((a, b) => a - b);
record("Search", searchTimings[2], 250);

// First render of the list after the data arrives.
await page.goto(`${WEB}/stories/${story.id}/wiki`);
await page.waitForSelector(".wiki-row-main");
const listPaint = await page.evaluate(() => {
	const nav = performance.getEntriesByType("navigation")[0];
	return performance.now() - (nav?.responseEnd ?? 0);
});
record("List first paint (incl. network)", listPaint, 2000);

// Detail render for one entity.
const detailStarted = Date.now();
await page.goto(`${WEB}/stories/${story.id}/wiki/${sample.id}`);
await page.waitForSelector(".wiki-detail-title h1");
record("Entity detail (incl. network)", Date.now() - detailStarted, 900);

// Detail payload alone, which is the part the UI controls.
const detailTimings = [];
for (let attempt = 0; attempt < 5; attempt += 1) {
	const started = Date.now();
	await (await fetch(`${API}/entities/${sample.id}`, { headers: { Cookie: cookie } })).json();
	detailTimings.push(Date.now() - started);
}
detailTimings.sort((a, b) => a - b);
record("Entity detail API", detailTimings[2], 150);

// Layout shift while the detail settles.
const shift = await page.evaluate(
	() =>
		new Promise((resolve) => {
			let total = 0;
			new PerformanceObserver((list) => {
				for (const entry of list.getEntries()) {
					if (!entry.hadRecentInput) total += entry.value;
				}
			}).observe({ type: "layout-shift", buffered: true });
			setTimeout(() => resolve(total), 1500);
		}),
);
record("Layout shift (×1000)", shift * 1000, 100);

await browser.close();

console.log(`\nStory: ${title} · ${sample ? `${sample.name} sampled` : "no entities"}\n`);
for (const row of results) {
	console.log(
		`${row.ok ? "PASS" : "FAIL"} ${row.name.padEnd(34)} ${String(row.ms).padStart(5)} ms  (target ${row.target} ms)`,
	);
}
const failures = results.filter((row) => !row.ok);
console.log(`\n${results.length - failures.length}/${results.length} within target`);
process.exit(failures.length ? 1 : 0);
