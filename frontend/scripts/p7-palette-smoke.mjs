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

const rawCookie = process.env.QA_COOKIE;
if (!rawCookie) throw new Error('Run this through phase7-qa.mjs so the shared QA account is signed in.');
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Palette ' + stamp }) }, rawCookie);
const chapter = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'Copper Morning', content: 'Mira Voss set the copper compass on the table. The room smelled of rain and tea. She waited for Hollis to speak.' }) }, rawCookie);
await request('/stories/' + story.id + '/entities', { method: 'POST', body: JSON.stringify({ name: 'Mira Voss', entity_type: 'character', summary: 'Compass keeper.' }) }, rawCookie);
for (let attempt = 0; attempt < 90; attempt += 1) {
	const status = await request('/stories/chapters/' + chapter.id + '/status', {}, rawCookie);
	if (status.index_status === 'indexed') break;
	if (status.index_status === 'failed') throw new Error('index failed: ' + status.index_error);
	await new Promise((resolve) => setTimeout(resolve, 500));
}

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
await page.locator('.cm-content').click();

await page.keyboard.press('Control+k');
await page.locator('.command-dialog').waitFor({ timeout: 10000 });
const optionText = await page.getByRole('option').allInnerTexts();
check('palette exposes primary actions', ['Run continuity check', 'Add fact from selection', 'Line focus', 'Typewriter mode', 'Editor theme'].every((label) => optionText.some((text) => text.includes(label))), optionText.slice(0, 6).join(' | '));
const footer = await page.locator('.command-footer').innerText();
check('palette shows keyboard hints', /esc/i.test(footer) && /Ctrl\/Cmd \+ K/i.test(footer), footer.replace(/\n/g, ' | '));
await page.keyboard.press('Escape');
await page.locator('.command-dialog').waitFor({ state: 'hidden', timeout: 5000 });
const restored = await page.evaluate(() => Boolean(document.activeElement?.closest('.cm-editor')));
check('Escape returns focus to the editor', restored);

await page.keyboard.press('Control+k');
await page.locator('.command-input').fill('copper compass');
await page.locator('.command-group', { hasText: 'Passages' }).waitFor({ timeout: 30000 });
const passages = await page.locator('.command-passage').allInnerTexts();
check('text search lists manuscript passages', passages.length > 0 && /copper compass/i.test(passages[0]), passages.slice(0, 2).join(' | '));
await page.locator('.command-passage').first().click();
await page.locator('.command-dialog').waitFor({ state: 'hidden', timeout: 5000 });
const focusedAfterPassage = await page.evaluate(() => Boolean(document.activeElement?.closest('.cm-editor')));
check('opening a passage returns to the manuscript', focusedAfterPassage);

await page.keyboard.press('Control+k');
await page.locator('.command-input').fill('Mira');
await page.locator('.command-group', { hasText: 'Entries' }).waitFor({ timeout: 10000 });
await page.getByRole('option').filter({ hasText: 'Mira Voss' }).first().click();
await page.waitForURL(/\/wiki\//, { timeout: 10000 });
check('entity search opens the entry page', page.url().includes('/wiki/'), page.url());

await page.goto(WEB + '/stories/' + story.id);
await page.locator('.cm-editor').waitFor({ timeout: 30000 });
await page.locator('.cm-content').click();
await page.keyboard.press('Control+k');
await page.getByRole('option').filter({ hasText: 'Editor theme' }).first().click();
await page.locator('.command-dialog').waitFor({ state: 'hidden', timeout: 5000 });
const theme = await page.evaluate(() => JSON.parse(localStorage.getItem('stillroom:editor-preferences') || '{}').theme);
check('palette can change the editor theme', theme === 'sepia' || theme === 'night', String(theme));
await page.keyboard.press('Control+k');
const recentText = await page.locator('.command-group', { hasText: 'Recent' }).innerText();
check('recents lead the empty palette', /Editor theme/.test(recentText), recentText.replace(/\n/g, ' | '));

check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id }));
if (failed.length) process.exit(1);