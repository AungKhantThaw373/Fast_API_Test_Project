import { chromium } from 'playwright';
import { apiHeaders, csrfToken } from './qa-csrf.mjs';

const WEB = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000';
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
async function noPageOverflow(page) {
	return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
}

const rawCookie = process.env.QA_COOKIE;
if (!rawCookie) throw new Error('Run this through phase7-qa.mjs so the shared QA account is signed in.');
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Accessibility ' + stamp }) }, rawCookie);
const first = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'The gate', content: 'Mira opens the gate.\nThe lantern is already lit.\n' }) }, rawCookie);
await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'The ledger', content: 'Mira reads the ledger.\nThe captain watches her.\n' }) }, rawCookie);
const thread = await request('/stories/' + story.id + '/threads', { method: 'POST', body: JSON.stringify({ title: 'Who lit the lantern?', description: 'Someone was here before Mira.', setup_chapter_id: first.id, linked_entity_ids: [] }) }, rawCookie);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
const [cookieName, cookieValue] = rawCookie.split('=');
await context.addCookies([{ name: cookieName, value: cookieValue, domain: '127.0.0.1', path: '/' }]);

await page.goto(WEB + '/stories/' + story.id);
await page.locator('.manuscript-surface').waitFor({ timeout: 30000 });
if (!(await page.getByRole('button', { name: /Export manuscript/ }).isVisible())) await page.locator('.mobile-file-menu > summary').click();
await page.getByRole('button', { name: /Export manuscript/ }).click();
await page.getByRole('dialog', { name: 'Export' }).waitFor();
check('export dialog takes focus', await page.evaluate(() => document.activeElement?.getAttribute('aria-label') === 'Close export panel'));
let trapped = true;
for (let i = 0; i < 12; i += 1) {
	await page.keyboard.press('Tab');
	if (!(await page.evaluate(() => Boolean(document.activeElement?.closest('.export-panel'))))) trapped = false;
}
check('Tab stays inside the export dialog', trapped);
trapped = true;
for (let i = 0; i < 6; i += 1) {
	await page.keyboard.press('Shift+Tab');
	if (!(await page.evaluate(() => Boolean(document.activeElement?.closest('.export-panel'))))) trapped = false;
}
check('Shift+Tab stays inside the export dialog', trapped);
await page.keyboard.press('Escape');
await page.getByRole('dialog', { name: 'Export' }).waitFor({ state: 'detached' });
check('Escape restores focus to the export trigger', await page.evaluate(() => Boolean(document.activeElement?.textContent?.includes('Export manuscript'))));

await page.locator('.manuscript-surface .cm-content').click();
await page.keyboard.press('Control+K');
await page.locator('.command-input').waitFor();
check('command palette focuses its search field', await page.evaluate(() => document.activeElement?.classList.contains('command-input')));
await page.keyboard.press('Escape');
await page.locator('.command-input').waitFor({ state: 'detached' });
await page.waitForTimeout(80);
check('palette returns focus to the writing surface', await page.evaluate(() => Boolean(document.activeElement?.closest('.manuscript-surface'))));

await page.setViewportSize({ width: 390, height: 844 });
await page.reload();
await page.locator('.manuscript-surface').waitFor({ timeout: 30000 });
check('phone studio does not overflow sideways', await noPageOverflow(page));
check('phone studio keeps the chapter picker and editor reachable', await page.locator('.mobile-chapter-picker').isVisible() && await page.locator('.manuscript-surface').isVisible());
if (!(await page.getByRole('button', { name: /Export manuscript/ }).isVisible())) await page.locator('.mobile-file-menu > summary').click();
await page.getByRole('button', { name: /Export manuscript/ }).click();
await page.getByRole('dialog', { name: 'Export' }).waitFor();
const panelBox = await page.locator('.export-panel').boundingBox();
check('phone export dialog fits the viewport', Boolean(panelBox && panelBox.x >= 0 && panelBox.x + panelBox.width <= 390 && panelBox.y >= 0), JSON.stringify(panelBox));
check('phone export dialog does not overflow sideways', await page.evaluate(() => { const panel = document.querySelector('.export-panel'); return panel ? panel.scrollWidth <= panel.clientWidth + 1 : false; }));
const tinyExport = await page.evaluate(() => Array.from(document.querySelectorAll('.export-panel *')).filter((element) => {
	const style = getComputedStyle(element);
	return element.children.length === 0 && (element.textContent || '').trim() && element.getBoundingClientRect().width > 0 && parseFloat(style.fontSize) < 12;
}).map((element) => element.tagName + ':' + (element.textContent || '').trim().slice(0, 25) + ':' + getComputedStyle(element).fontSize));
check('export text respects the 12px floor', tinyExport.length === 0, tinyExport.slice(0, 4).join(' | '));
await page.getByRole('button', { name: 'Close export panel' }).click();

await page.goto(WEB + '/stories/' + story.id + '/wiki/threads');
await page.locator('.thread-board').waitFor({ timeout: 30000 });
check('phone thread board does not overflow the page', await noPageOverflow(page));
const board = await page.locator('.thread-board').evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }));
check('phone thread board scrolls between columns', board.scroll > board.client, JSON.stringify(board));
check('all four thread columns exist on phone', (await page.locator('.thread-board-column').count()) === 4);
const tinyBoard = await page.evaluate(() => Array.from(document.querySelectorAll('.thread-board *')).filter((element) => {
	const style = getComputedStyle(element);
	return element.children.length === 0 && (element.textContent || '').trim() && element.getBoundingClientRect().width > 0 && parseFloat(style.fontSize) < 12;
}).map((element) => element.tagName + ':' + (element.textContent || '').trim().slice(0, 25) + ':' + getComputedStyle(element).fontSize));
check('thread board text respects the 12px floor', tinyBoard.length === 0, tinyBoard.slice(0, 4).join(' | '));

await page.setViewportSize({ width: 1200, height: 900 });
await page.reload();
await page.locator('.thread-board').waitFor({ timeout: 30000 });
await page.locator('.thread-drag-handle').focus();
await page.keyboard.press('Space');
await page.waitForTimeout(250);
await page.keyboard.press('ArrowRight');
await page.waitForTimeout(250);
await page.keyboard.press('ArrowRight');
await page.waitForTimeout(250);
await page.keyboard.press('Space');
await page.locator('.thread-resolve-dialog').waitFor({ timeout: 15000 });
await page.waitForTimeout(150);
check('keyboard drag can open the payoff dialog', true);
check('payoff dialog focuses its chapter choice', await page.evaluate(() => document.activeElement?.tagName === 'SELECT'));
trapped = true;
for (let i = 0; i < 8; i += 1) {
	await page.keyboard.press(i % 2 ? 'Shift+Tab' : 'Tab');
	if (!(await page.evaluate(() => Boolean(document.activeElement?.closest('.thread-resolve-dialog'))))) trapped = false;
}
check('Tab stays inside the payoff dialog', trapped);
await page.keyboard.press('Escape');
await page.locator('.thread-resolve-dialog').waitFor({ state: 'detached' });
check('Escape closes the payoff dialog and restores the drag handle', await page.evaluate(() => document.activeElement?.classList.contains('thread-drag-handle')));

await page.setViewportSize({ width: 720, height: 900 });
await page.goto(WEB + '/stories/' + story.id);
await page.locator('.manuscript-surface').waitFor({ timeout: 30000 });
check('200% width studio reflows without page scrolling', await noPageOverflow(page));

check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, story: story.id, thread: thread.id }));
if (failed.length) process.exit(1);