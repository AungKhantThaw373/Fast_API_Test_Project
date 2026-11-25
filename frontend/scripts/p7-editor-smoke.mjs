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

const email = 'p7smoke' + stamp + '@example.com';
await request('/register', { method: 'POST', body: JSON.stringify({ username: 'p7smoke' + stamp, email, password: PASSWORD }) });
const token = await fetch(API + '/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const rawCookie = (token.headers.get('set-cookie') || '').split(';')[0];
if (!rawCookie) throw new Error('no cookie');
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Phase 7 smoke ' + stamp }) }, rawCookie);
await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'First Light', content: 'A short opening chapter.' }) }, rawCookie);
const paragraphs = [];
for (let index = 0; index < 950; index += 1) paragraphs.push('Paragraph ' + index + ' follows Mira through the quiet yard, counting lanterns and listening for the gate.');
const longContent = paragraphs.join('\n\n');
const longChapter = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'The Long Night', content: longContent }) }, rawCookie);

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
const started = Date.now();
await page.goto(WEB + '/stories/' + story.id);
await page.locator('.cm-editor').waitFor({ timeout: 30000 });
check('editor mounts', await page.locator('.cm-editor').isVisible(), (Date.now() - started) + 'ms');
await page.locator('.chapter-nav-item', { hasText: 'The Long Night' }).click();
await page.locator('.cm-content').click();
await page.keyboard.press('Control+End');
await page.getByText('Paragraph 949', { exact: false }).waitFor({ timeout: 30000 });
const countText = await page.locator('.editor-toolbar-right').innerText();
check('100k-character chapter loads', /\d[\d,]{4,} words/.test(countText), countText);
const typedStarted = Date.now();
await page.keyboard.type('x'.repeat(120));
const perKey = (Date.now() - typedStarted) / 120;
check('typing stays responsive', perKey < 16, perKey.toFixed(2) + 'ms/key');
await page.waitForTimeout(900);
check('word count updates after debounce', /words/.test(await page.locator('.editor-toolbar-right').innerText()));

await page.keyboard.press('Control+z');
await page.waitForTimeout(250);
check('undo works before reload', !(await page.locator('.cm-content').textContent()).endsWith('x'.repeat(120)));
await page.keyboard.type(' tail-marker');
await page.waitForTimeout(900);
await page.keyboard.press('Control+s');
await page.waitForTimeout(700);

await page.reload();
await page.locator('.cm-editor').waitFor({ timeout: 30000 });
await page.locator('.cm-content').click();
await page.keyboard.press('Control+End');
await page.keyboard.press('Control+z');
await page.waitForTimeout(300);
const afterReload = await page.locator('.cm-content').textContent();
check('undo history survives reload', !afterReload.includes('tail-marker'), afterReload.slice(-80));
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));

await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id, longChapter: longChapter.id, msPerKey: perKey }));
if (failed.length) process.exit(1);