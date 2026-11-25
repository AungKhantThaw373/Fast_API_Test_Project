import { chromium } from 'playwright';
import { apiHeaders, csrfToken } from './qa-csrf.mjs';

const WEB = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000';
const stamp = Date.now();
const PASSWORD = 'correct horse battery';
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

const email = 'p8qa' + stamp + '@example.com';
await request('/register', { method: 'POST', body: JSON.stringify({ username: 'p8qa' + stamp, email, password: PASSWORD }) });
const token = await fetch(API + '/token', { method: 'POST', headers: { ...apiHeaders(csrf), 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const rawCookie = (token.headers.get('set-cookie') || '').split(';')[0];
if (!rawCookie) throw new Error('no auth cookie');
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Phase 8 diagnostics ' + stamp }) }, rawCookie);
await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'First Light', content: 'A short opening chapter.' }) }, rawCookie);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
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
await page.locator('.diagnostic-card').first().waitFor({ timeout: 30000 });
const cards = await page.locator('.diagnostic-card').count();
check('diagnostics renders four cards', cards === 4, String(cards));
check('database is healthy', (await page.locator('.diagnostic-card').first().innerText()).includes('Healthy'));
check('queue counts render', (await page.locator('.diagnostic-card').nth(1).innerText()).includes('Queued'));
check('backup is reported', (await page.locator('.diagnostic-card').nth(3).innerText()).match(/dump|No dump found/) !== null);
check('model status renders', !(await page.locator('.diagnostic-card').nth(2).innerText()).includes('undefined'));
check('csrf cookie is readable', await page.evaluate(() => document.cookie.includes('csrf=')));
const cookies = await context.cookies(WEB);
const auth = cookies.find((cookie) => cookie.name === 'token');
check('auth cookie is HttpOnly', Boolean(auth?.httpOnly), auth?.name || 'missing');
check('diagnostics page has no JS errors', errors.length === 0, errors.join('; '));

await page.goto(WEB + '/settings');
await page.getByRole('heading', { name: 'Settings' }).waitFor({ timeout: 30000 });
check('session list renders', await page.getByText('Where you are signed in', { exact: false }).isVisible());
check('audit list renders', await page.getByText('Activity', { exact: false }).first().isVisible());
const downloadPromise = page.waitForEvent('download', { timeout: 60000 });
await page.getByRole('link', { name: /Export all my data/ }).click();
const download = await downloadPromise;
check('account export downloads a zip', download.suggestedFilename().endsWith('.zip'), download.suggestedFilename());

const headers = await fetch(API + '/health');
check('API sends nosniff', headers.headers.get('x-content-type-options') === 'nosniff');
check('API sends frame denial', headers.headers.get('x-frame-options') === 'DENY');

await browser.close();
const failed = results.filter((result) => !result.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length }));
if (failed.length) process.exit(1);