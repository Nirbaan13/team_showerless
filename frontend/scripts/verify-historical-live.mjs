// Real local-stack acceptance only: no fulfilled routes or generated image fixtures.
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.HISTORICAL_FRONTEND_URL || 'http://127.0.0.1:18203';
const runtime = process.env.HISTORICAL_RUNTIME || '/tmp/ivan-historical-runtime/wise0855-3';
const output = process.env.HISTORICAL_BROWSER_OUTPUT || '/tmp/ivan-historical-runtime/browser-wise0855';
await fs.mkdir(output, { recursive: false });
const selection = JSON.parse(await fs.readFile(path.join(runtime, 'selection.json'), 'utf8'));
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
const errors = [], requests = [], apiResponses = [];
page.on('pageerror', error => errors.push(String(error)));
page.on('request', request => {
  if (request.url().startsWith(base + '/backend/')) requests.push({ method: request.method(), url: request.url(), body: request.postData() });
});
page.on('response', async response => {
  if (response.url().startsWith(base + '/backend/')) apiResponses.push({ url: response.url(), status: response.status() });
});
try {
  await page.goto(base + '/?tab=viewer');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByLabel('RA (deg)', { exact: true }).fill('133.795125');
  await page.getByLabel('Dec (deg)', { exact: true }).fill('-7.245139');
  await page.getByLabel('Archive', { exact: true }).selectOption('unwise-neo11');
  const period = page.locator('#tutorial-target-epoch');
  if (await period.getAttribute('open') === null) await period.locator('summary').click();
  await page.getByLabel('Observed from', { exact: true }).fill('2010-01-01');
  await page.getByLabel('Observed through', { exact: true }).fill('2024-12-31');
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  for (const observation of selection.observations) {
    await page.getByRole('checkbox', { name: `Select observation ${observation.native_id}`, exact: true }).check({ timeout: 180000 });
  }
  await page.getByRole('button', { name: 'Download selected (8)', exact: true }).click();
  await page.getByText('Download: completed', { exact: true }).waitFor({ timeout: 180000 });
  const action = page.getByRole('button', { name: 'Find historical motion', exact: true });
  await action.waitFor();
  if (await action.isDisabled()) throw new Error('Historical action remains disabled after real selected download');
  const renderedResponse = page.waitForResponse(response => response.url().endsWith('/backend/api/motion/search') && response.request().method() === 'POST');
  await action.click();
  const result = page.getByRole('region', { name: 'Historical motion result', exact: true });
  await result.waitFor({ timeout: 180000 });
  const images = await result.locator('img').evaluateAll(nodes => nodes.map(node => ({ loaded: node.complete && node.naturalWidth > 0, width: node.naturalWidth, height: node.naturalHeight })));
  if (!images.length || images.some(image => !image.loaded)) throw new Error('Real historical PNGs did not decode in browser');
  const text = await result.innerText();
  if (!text.includes('2010') || !text.includes('2024') || !(text.includes('arcsec/year') || text.includes('″/year'))) throw new Error('Actual dates or physical yearly units missing');
  if (errors.length) throw new Error(errors.join('\n'));
  await result.scrollIntoViewIfNeeded();
  await result.screenshot({ path: path.join(output, 'historical-result.png') });
  const reviewRequest = requests.find(request => request.url.endsWith('/backend/api/motion/search') && request.method === 'POST');
  if (!reviewRequest) throw new Error('No same-origin Scala → Ivan review request');
  const reviewResponse = await renderedResponse;
  if (!reviewResponse.ok()) throw new Error('Browser same-origin scientific result request failed');
  await fs.writeFile(path.join(output, 'ivan-review.json'), await reviewResponse.body());
  await fs.writeFile(path.join(output, 'browser-proof.json'), JSON.stringify({ status: 'PASS', source: 'real unWISE neo11 W2', base, runtime, images, requests, apiResponses, errors, resultText: text }, null, 2));
  console.log(JSON.stringify({ status: 'PASS', decodedImages: images.length, errors, output }));
} catch (error) {
  await fs.writeFile(path.join(output, 'failure.txt'), String(error));
  await fs.writeFile(path.join(output, 'page.txt'), await page.locator('body').innerText());
  await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
  throw error;
} finally {
  await browser.close();
}
