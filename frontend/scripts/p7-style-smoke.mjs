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
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Style ' + stamp }) }, rawCookie);
const content = [
	'Mira really noticed the copper compass on the table.',
	'She quickly saw that the letter was taken before dawn.',
	'She walked to the window. She walked back to the desk. She walked outside.',
	'The room was cold, and the door was covered in frost.',
	'He is certain now. She has the key. They are ready.',
].join('\n\n');
const chapter = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'Quiet Line', content }) }, rawCookie);

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
await page.locator('.cm-content').waitFor({ timeout: 30000 });
const before = await page.locator('.cm-content').innerText();

await page.locator('.desk-toggle').click();
await page.getByRole('tab', { name: /Review/ }).click();
await page.getByRole('tab', { name: 'Style' }).click();
await page.locator('.style-panel').waitFor({ timeout: 10000 });
const stats = await page.locator('.style-stats').innerText();
check('style panel reports readability', /Reading ease/.test(stats) && /Grade/.test(stats), stats.replace(/\n/g, ' | '));
const categories = await page.locator('.style-filter').allInnerTexts();
check('style panel finds multiple observation families', ['Crutch words', 'Filter words', 'Adverbs', 'Repeated openings', 'Passive voice'].every((label) => categories.some((text) => text.includes(label))), categories.join(' | '));
const issueCount = await page.locator('.style-group li').count();
check('style panel lists observations', issueCount >= 6, String(issueCount));

await page.locator('.style-find').first().click();
const selected = await page.evaluate(() => window.getSelection()?.toString() ?? '');
check('clicking an observation selects it in the manuscript', selected.trim().length > 0, selected);
const markCount = await page.locator('.cm-style-mark').count();
check('observations underline the manuscript', markCount > 0, String(markCount));
await page.locator('.cm-style-mark').first().click();
const selectedFromMark = await page.evaluate(() => window.getSelection()?.toString() ?? '');
check('clicking a mark selects its text', selectedFromMark.trim().length > 0, selectedFromMark);

const firstCategory = await page.locator('.style-group h3').first().innerText();
const groupBefore = await page.locator('.style-group li').count();
await page.getByRole('button', { name: 'Dismiss this' }).first().click();
const groupAfter = await page.locator('.style-group li').count();
check('dismissing one instance hides only it', groupAfter === groupBefore - 1, `${groupBefore} -> ${groupAfter}`);
await page.getByRole('button', { name: 'Restore all' }).click();
await page.getByRole('button', { name: 'Mute pattern' }).first().click();
const afterMute = await page.locator('.style-group li').count();
check('muting a pattern hides its instances', afterMute < groupBefore, `${groupBefore} -> ${afterMute} (${firstCategory.trim()})`);
await page.getByRole('button', { name: 'Restore all' }).click();
const restored = await page.locator('.style-group li').count();
check('restoring brings observations back', restored === groupBefore, `${groupBefore} -> ${restored}`);

const after = await page.locator('.cm-content').innerText();
check('style analysis never edits the manuscript', before === after, `${before.length} -> ${after.length} chars`);
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id, chapter: chapter.id }));
if (failed.length) process.exit(1);