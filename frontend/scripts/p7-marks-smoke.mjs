import { chromium } from 'playwright';

const WEB = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000';
const stamp = Date.now();
const PASSWORD = 'correct horse battery';

async function request(path, options = {}, cookie) {
	const response = await fetch(API + path, { ...options, headers: { 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}), ...options.headers } });
	const text = await response.text();
	if (!response.ok) throw new Error(options.method + ' ' + path + ' -> ' + response.status + ' ' + text);
	return text ? JSON.parse(text) : null;
}

const email = 'p7marks' + stamp + '@example.com';
await request('/register', { method: 'POST', body: JSON.stringify({ username: 'p7marks' + stamp, email, password: PASSWORD }) });
const token = await fetch(API + '/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const rawCookie = (token.headers.get('set-cookie') || '').split(';')[0];
await request('/ai-settings', { method: 'PUT', body: JSON.stringify({ provider: 'ollama', model: 'qwen3:4b-instruct', base_url: 'http://127.0.0.1:11434' }) }, rawCookie);
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Phase 7 marks ' + stamp }) }, rawCookie);
await request('/stories/' + story.id, { method: 'PATCH', body: JSON.stringify({ external_analysis_enabled: true, monthly_ai_budget: 5, scan_interval_words: 2000 }) }, rawCookie);
const first = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'The Gate', content: "Mira Voss crossed the yard at dawn. Mira's eyes were blue. She carried a brass lantern. Hollis waited by the well." }) }, rawCookie);
const second = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'Night Watch', content: "Mira's eyes were green. The brass lantern was cold. Hollis said the gate had been open all night." }) }, rawCookie);
await request('/stories/' + story.id + '/entities', { method: 'POST', body: JSON.stringify({ name: 'Mira Voss', entity_type: 'character', summary: 'A lantern-bearer who keeps watch at the gate.', aliases: [{ alias: 'Mira', alias_type: 'name' }] }) }, rawCookie);
const lantern = await request('/stories/' + story.id + '/entities', { method: 'POST', body: JSON.stringify({ name: 'brass lantern', entity_type: 'item', summary: 'Mira carries it after dusk.', aliases: [{ alias: 'lantern', alias_type: 'name' }] }) }, rawCookie);
for (const chapter of [first, second]) {
	for (let index = 0; index < 90; index += 1) {
		const status = await request('/stories/chapters/' + chapter.id + '/status', {}, rawCookie);
		if (status.index_status === 'indexed') break;
		if (status.index_status === 'failed') throw new Error('index failed: ' + status.index_error);
		await new Promise((resolve) => setTimeout(resolve, 500));
	}
}
let scan = null;
for (let attempt = 0; attempt < 60; attempt += 1) {
	try {
		scan = await request('/stories/chapters/' + second.id + '/scan?force=true', { method: 'POST' }, rawCookie);
		break;
	} catch (error) {
		if (!String(error).includes('still being indexed')) throw error;
		await new Promise((resolve) => setTimeout(resolve, 1000));
	}
}
if (!scan) throw new Error('chapter never became ready for a scan');
console.log('scan', JSON.stringify(scan));

const results = [];
function check(name, condition, detail = '') {
	results.push({ name, ok: Boolean(condition), detail });
	console.log((condition ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : ''));
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
const [name, value] = rawCookie.split('=');
await page.context().addCookies([{ name, value, domain: '127.0.0.1', path: '/' }]);
await page.goto(WEB + '/stories/' + story.id);
await page.locator('.cm-editor').waitFor({ timeout: 30000 });
await page.locator('.chapter-nav-item', { hasText: 'Night Watch' }).click();
await page.locator('.cm-entity-mark').first().waitFor({ timeout: 15000 });
const marks = await page.locator('.cm-entity-mark').count();
check('entity marks render', marks >= 2, String(marks));
await page.locator('.chapter-nav-item', { hasText: 'The Gate' }).click();
await page.locator('.cm-entity-mark', { hasText: 'brass lantern' }).first().waitFor({ timeout: 15000 });
await page.locator('.cm-entity-mark', { hasText: 'brass lantern' }).first().hover();
await page.locator('.cm-canon-entity').waitFor({ timeout: 5000 });
const card = await page.locator('.cm-canon-entity').innerText();
check('hover shows canon card', /brass lantern/i.test(card), card.replace(/\n/g, ' | '));

if (scan.finding_count > 0) {
	await page.locator('.chapter-nav-item', { hasText: 'Night Watch' }).click();
	await page.locator('.cm-editor').waitFor({ timeout: 30000 });
	await page.locator('.cm-finding-mark').first().waitFor({ timeout: 15000 });
	await page.locator('.cm-finding-mark').first().click();
	await page.locator('.cm-canon-finding').waitFor({ timeout: 5000 });
	const actions = await page.locator('.cm-popover-actions button').allInnerTexts();
	check('finding popover offers review actions', ['Resolve', 'Dismiss', 'Intentional', 'Open evidence'].every((label) => actions.includes(label)), actions.join(','));
	check('gutter finding marker is visible', await page.locator('.cm-finding-gutter-dot').first().isVisible());
	check('finding navigation is visible', await page.locator('.cm-finding-nav').isVisible());
} else {
	console.log('INFO scan produced no findings; mark-specific checks skipped');
}

if (await page.locator('.cm-canon-popover').count()) await page.locator('.cm-canon-popover .cm-popover-close').click();
await page.locator('.chapter-nav-item', { hasText: 'The Gate' }).click();
await page.locator('.cm-entity-mark', { hasText: 'brass lantern' }).first().waitFor({ timeout: 15000 });
await page.locator('.cm-entity-mark', { hasText: 'brass lantern' }).first().click();
await page.waitForTimeout(1500);
const entityUrl = page.url();
const dialogs = await page.locator('[role="dialog"]').allInnerTexts();
check('clicking entity mark opens its page', entityUrl.includes('/wiki/' + lantern.id), entityUrl + (dialogs.length ? ' dialogs: ' + dialogs.join(' | ') : ''));
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));

await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id, findings: scan.finding_count }));
if (failed.length) process.exit(1);