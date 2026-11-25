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

const rawCookie = process.env.QA_COOKIE;
if (!rawCookie) throw new Error('Run this through phase7-qa.mjs so the shared QA account is signed in.');
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Recaps ' + stamp }) }, rawCookie);
const chapters = [];
for (let number = 1; number <= 3; number += 1) {
	const content = `Mira opens the ${number === 1 ? 'gate' : 'ledger'} in chapter ${number}. The lamp is already lit. She hears rain on the roof.`;
	chapters.push(await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'Chapter ' + number, content }) }, rawCookie));
}
const arc = await request('/stories/' + story.id + '/arcs', { method: 'POST', body: JSON.stringify({ name: 'The gate' }) }, rawCookie);
await request('/stories/' + story.id + '/arcs', { method: 'PUT', body: JSON.stringify({ arc_id: arc.id, chapter_ids: chapters.map((chapter) => chapter.id) }) }, rawCookie);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
const [name, value] = rawCookie.split('=');
await page.context().addCookies([{ name, value, domain: '127.0.0.1', path: '/' }]);
await page.goto(WEB + '/stories/' + story.id);
await page.locator('.cm-content').waitFor({ timeout: 30000 });

await page.getByRole('tab', { name: 'Recap' }).click();
await page.locator('.recap-panel').waitFor({ timeout: 10000 });
const editor = page.locator('.recap-editor');
await editor.waitFor({ timeout: 10000 });
await page.waitForFunction(() => (document.querySelector('.recap-editor')?.value || '').length > 0);
const initial = await editor.inputValue();
check('chapter synopsis is present', initial.includes('Mira opens the gate'), initial.slice(0, 80));

const savedText = 'Mira enters the gatehouse and finds the lamp already burning.';
await editor.fill(savedText);
await page.getByRole('button', { name: 'Save synopsis' }).click();
await page.waitForFunction(() => document.querySelector('.recap-editor')?.value === 'Mira enters the gatehouse and finds the lamp already burning.');
check('synopsis saves from the desk', true);

await page.reload();
await page.locator('.cm-content').waitFor({ timeout: 30000 });
await page.getByRole('tab', { name: 'Recap' }).click();
await page.locator('.recap-editor').waitFor({ timeout: 10000 });
await page.waitForFunction(() => (document.querySelector('.recap-editor')?.value || '').length > 0);
check('edited synopsis survives a reload', (await page.locator('.recap-editor').inputValue()) === savedText);

const regenerate = page.getByRole('button', { name: 'Regenerate' });
if (await regenerate.count()) {
	await regenerate.click();
	await page.waitForFunction((expected) => document.querySelector('.recap-editor')?.value !== expected, savedText);
	check('regenerate replaces the synopsis from chapter text', true);
} else {
	check('regenerate replaces the synopsis from chapter text', false, 'button missing');
}

await page.locator('.recap-list li').first().waitFor({ timeout: 10000 });
const rows = await page.locator('.recap-list li').count();
check('story so far lists the recent chapters', rows === 3, String(rows));
const citations = await page.locator('.recap-citation').count();
check('each recap row carries a citation', citations === 3, String(citations));
const range = await page.locator('.recap-range').innerText();
check('recap range is explicit', /Chapters 1–3/i.test(range), range);

const summarize = page.getByRole('button', { name: 'Summarize arc' });
if (await summarize.count()) {
	await summarize.click();
	await page.locator('.recap-arc-summary').waitFor({ timeout: 10000 });
	const arcText = await page.locator('.recap-arc-summary').innerText();
	check('arc summary is built from chapter synopses', arcText.includes('Chapter 1') && arcText.length > 40, arcText.slice(0, 90));
} else {
	check('arc summary is built from chapter synopses', false, 'button missing');
}

const arcRows = (await request('/stories/' + story.id + '/arcs', {}, rawCookie));
check('arc summary is stored on the arc', (arcRows.find((row) => row.id === arc.id)?.summary || '').includes('Chapter 2'));

await page.locator('.recap-citation').last().click();
await page.waitForTimeout(250);
const selected = await page.locator('.chapter-nav-item.selected').innerText();
check('citation opens the cited chapter', selected.includes('Chapter 3'), selected.replace(/\n/g, ' | '));
const paneClosed = await page.locator('.recap-panel').count();
check('citation returns to the manuscript', paneClosed === 0, String(paneClosed));

check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id }));
if (failed.length) process.exit(1);