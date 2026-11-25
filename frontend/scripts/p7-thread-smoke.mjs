import { chromium } from 'playwright';
import { apiHeaders, csrfToken } from './qa-csrf.mjs';

const WEB = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000';
const stamp = Date.now();
const csrf = await csrfToken(API);

async function request(path, options = {}, cookie) {
	const response = await fetch(API + path, { ...options, headers: { ...apiHeaders(csrf, cookie), ...options.headers } });
	const text = await response.text();
	if (!response.ok) throw new Error(options.method + ' ' + path + ' -> ' + response.status + ' ' + text);
	return text ? JSON.parse(text) : null;
}

const results = [];
function check(name, condition, detail = '') {
	results.push({ name, ok: Boolean(condition), detail });
	console.log((condition ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : ''));
}

async function dragTo(page, source, target) {
	const a = await source.boundingBox();
	const b = await target.boundingBox();
	if (!a || !b) throw new Error('drag source or target missing');
	await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
	await page.mouse.down();
	await page.mouse.move(a.x + a.width / 2 + 8, a.y + a.height / 2 + 8, { steps: 4 });
	await page.mouse.move(b.x + b.width / 2, b.y + 70, { steps: 18 });
	await page.mouse.up();
}

const rawCookie = process.env.QA_COOKIE;
if (!rawCookie) throw new Error('Run this through phase7-qa.mjs so the shared QA account is signed in.');
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Threads ' + stamp }) }, rawCookie);
const first = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'The gate', content: 'Mira opens the gate.\nThe lantern is already lit.\n' }) }, rawCookie);
const second = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'The ledger', content: 'Mira reads the ledger.\nThe captain watches her.\n' }) }, rawCookie);
const entity = await request('/stories/' + story.id + '/entities', { method: 'POST', body: JSON.stringify({ name: 'Mira Voss', entity_type: 'character' }) }, rawCookie);
const arc = await request('/stories/' + story.id + '/arcs', { method: 'POST', body: JSON.stringify({ name: 'The gate' }) }, rawCookie);
await request('/stories/' + story.id + '/arcs', { method: 'PUT', body: JSON.stringify({ arc_id: arc.id, chapter_ids: [first.id, second.id] }) }, rawCookie);
const thread = await request('/stories/' + story.id + '/threads', { method: 'POST', body: JSON.stringify({ title: 'Who lit the lantern?', description: 'Someone was here before Mira.', setup_chapter_id: first.id, setup_quote: 'The lantern is already lit.', linked_entity_ids: [entity.id] }) }, rawCookie);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
const [name, value] = rawCookie.split('=');
await page.context().addCookies([{ name, value, domain: '127.0.0.1', path: '/' }]);
await page.goto(WEB + '/stories/' + story.id + '/wiki/threads');
await page.locator('.thread-board').waitFor({ timeout: 30000 });

const columns = await page.locator('.thread-board-column h2').allInnerTexts();
check('four state columns are present', JSON.stringify(columns) === JSON.stringify(['Open', 'Touched', 'Resolved', 'Abandoned']), columns.join(' | '));
const card = page.locator('.thread-board-column.state-open .thread-board-card').first();
await card.waitFor({ timeout: 10000 });
check('card shows title, linked entity, setup', (await card.innerText()).includes('Who lit the lantern?') && (await card.innerText()).includes('Mira Voss') && (await card.innerText()).includes('Ch. 1'), (await card.innerText()).replace(/\n/g, ' | '));

await dragTo(page, page.locator('.thread-board-column.state-open .thread-drag-handle'), page.locator('.thread-board-column.state-touched'));
await page.locator('.thread-board-column.state-touched .thread-board-card').waitFor({ timeout: 10000 });
check('dragging Open → Touched moves the card', (await page.locator('.thread-board-column.state-open .thread-board-card').count()) === 0);

await dragTo(page, page.locator('.thread-board-column.state-touched .thread-drag-handle'), page.locator('.thread-board-column.state-resolved'));
await page.locator('.thread-resolve-dialog').waitFor({ timeout: 10000 });
check('resolving asks for a payoff chapter', (await page.locator('.thread-resolve-dialog').innerText()).includes('Which chapter pays this off?'), '');
await page.locator('.thread-resolve-dialog select').selectOption({ label: '2. The ledger' });
await page.getByRole('button', { name: 'Mark resolved' }).click();
await page.locator('.thread-board-column.state-resolved .thread-board-card').waitFor({ timeout: 10000 });
check('resolved card lands in its column', true);
let saved = (await request('/stories/' + story.id + '/threads', {}, rawCookie)).threads.find((row) => row.id === thread.id);
check('resolved state stores the payoff chapter', saved.state === 'resolved' && saved.payoff_chapter_id === second.id, saved.state + ' / ' + (saved.payoff_chapter_id || 'none'));

await dragTo(page, page.locator('.thread-board-column.state-resolved .thread-drag-handle'), page.locator('.thread-board-column.state-abandoned'));
await page.locator('.thread-board-column.state-abandoned .thread-board-card').waitFor({ timeout: 10000 });
check('dragging Resolved → Abandoned moves the card', true);
saved = (await request('/stories/' + story.id + '/threads', {}, rawCookie)).threads.find((row) => row.id === thread.id);
check('abandoned state persists', saved.state === 'abandoned', saved.state);

await page.locator('.thread-board-filters select').first().selectOption({ label: 'The gate' });
await page.waitForTimeout(500);
const arcCount = await page.locator('.thread-board-card').count();
check('arc filter keeps a matching thread', arcCount === 1, String(arcCount));
await page.locator('.thread-board-filters select').nth(1).selectOption({ label: 'Mira Voss' });
await page.waitForTimeout(300);
const entityCount = await page.locator('.thread-board-card').count();
check('entity filter keeps a matching thread', entityCount === 1, String(entityCount));
await page.getByRole('button', { name: 'Clear filters' }).click();
check('clear filters restores the board', (await page.locator('.thread-board-card').count()) === 1);

check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id }));
if (failed.length) process.exit(1);