import { chromium } from 'playwright';
import { apiHeaders, csrfToken } from './qa-csrf.mjs';

const WEB = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000';
const PASSWORD = 'correct horse battery';
const stamp = Date.now();
const csrf = await csrfToken(API);
const results = [];
function check(name, condition, detail = '') {
	results.push({ name, ok: Boolean(condition), detail });
	console.log((condition ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : ''));
}

async function request(path, options = {}, cookie) {
	const response = await fetch(API + path, { ...options, headers: { ...apiHeaders(csrf, cookie), ...options.headers } });
	const text = await response.text();
	if (!response.ok) throw new Error((options.method || 'GET') + ' ' + path + ' -> ' + response.status + ' ' + text);
	return text ? JSON.parse(text) : null;
}

const email = 'p9storage' + stamp + '@example.com';
await request('/register', { method: 'POST', body: JSON.stringify({ username: 'p9storage' + stamp, email, password: PASSWORD }) });
const token = await fetch(API + '/token', { method: 'POST', headers: { ...apiHeaders(csrf), 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const rawCookie = (token.headers.get('set-cookie') || '').split(';')[0];
if (!rawCookie) throw new Error('no auth cookie');
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Storage QA ' + stamp }) }, rawCookie);
const kept = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'Kept', content: 'One kept chapter with a little prose.' }) }, rawCookie);
const trashed = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'Trashed', content: 'One trashed chapter.' }) }, rawCookie);
await request('/stories/chapters/' + trashed.id, { method: 'DELETE' }, rawCookie);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
await page.goto(WEB + '/login');
await page.getByLabel('Email').fill(email);
await page.getByLabel('Password').fill(PASSWORD);
await page.getByRole('button', { name: 'Sign in' }).click();
await page.waitForURL('**/dashboard', { timeout: 30000 });

await page.goto(WEB + '/diagnostics');
await page.getByRole('heading', { name: 'Diagnostics' }).waitFor({ timeout: 30000 });
const storage = page.locator('.diagnostics-storage');
await storage.waitFor({ timeout: 30000 });
const text = await storage.innerText();
check('storage card renders database size', /in PostgreSQL/.test(text));
check('storage counts include the kept chapter', text.includes('Chapters') && text.includes('1'));
check('retention copy states 30 days', (text.match(/30 days/g) || []).length >= 2);
check('largest tables include story_chunks', text.includes('story_chunks'));
check('trashed chapter is shown', text.includes('Trashed chapters') && text.includes('1'));
check('cleanup is disabled with nothing expired', await page.getByRole('button', { name: 'Nothing expired' }).isDisabled());
check('cleanup note does not promise immediate shrink', text.includes('does not run a blocking VACUUM'));
check('storage page has no JS errors', errors.length === 0, errors.join('; '));
check('kept chapter still exists', Boolean(kept.id));

await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(200);
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
const offenders = overflow ? await page.evaluate(() => [...document.querySelectorAll('*')].filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 8).map((element) => element.tagName + '.' + element.className)) : [];
check('storage page has no horizontal overflow at 390px', !overflow, offenders.join(' | '));

await browser.close();
const failed = results.filter((result) => !result.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length }));
if (failed.length) process.exit(1);