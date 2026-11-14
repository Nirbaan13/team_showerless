const fs = require('node:fs');
const assert = require('node:assert/strict');
const { firefox } = require('/home/usatovpavel/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core');

(async () => {
  const browser = await firefox.launch({ headless: true });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto('http://144.124.238.101:8080/', { waitUntil: 'networkidle' });
    await page.getByRole('link', { name: 'ML analysis', exact: true }).click();
    await page.getByRole('heading', { name: 'Motion analysis', exact: true }).waitFor();
    await page.getByText('spherex-track-rf-v2', { exact: true }).waitFor();
    await page.getByText('Detection settings', { exact: true }).click();
    await page.getByLabel('Minimum residual S/N', { exact: true }).fill('4.25');
    const accepted = page.waitForResponse(response => response.url().endsWith('/api/analyses/motion') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Run analysis', exact: true }).click();
    const acceptance = await (await accepted).json();
    await page.getByRole('heading', { name: /candidate tracks · 4 exposures/ }).waitFor({ timeout: 120000 });
    const job = await (await page.request.get('http://144.124.238.101/api/analyses/' + acceptance.id)).json();
    assert.equal(job.status, 'completed');
    assert.equal(job.result.model.sha256, 'dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9');
    assert.equal(await page.locator('.inference-candidate').count(), job.result.candidates.length);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('.inference-image img')).every(image => image.complete && image.naturalWidth > 0));
    assert.ok(await page.locator('.inference-image svg circle').count());
    await page.locator('.inference-candidate-list select').selectOption('baseline');
    assert.match(await page.locator('.inference-candidate').first().innerText(), /heuristic #1/);
    await page.screenshot({ path: '/tmp/spaceapps-ml-v2-browser-prod.png', fullPage: true });
    await page.getByLabel('Minimum residual S/N', { exact: true }).fill('100');
    await page.getByRole('button', { name: 'Run analysis', exact: true }).click();
    await page.getByRole('heading', { name: '0 candidate tracks · 4 exposures', exact: true }).waitFor({ timeout: 120000 });
    await page.getByText('No candidate met the selected detection and motion thresholds.', { exact: true }).waitFor();
    await page.locator('form select').first().selectOption('download');
    await page.getByLabel('Download ID', { exact: true }).fill('browser-missing-download');
    await page.getByRole('button', { name: 'Run analysis', exact: true }).click();
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').innerText(), /not found/i);
    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
    mobile.on('pageerror', error => errors.push(String(error)));
    await mobile.goto('http://144.124.238.101:8080/', { waitUntil: 'networkidle' });
    await mobile.getByRole('button', { name: 'Open mobile navigation menu', exact: true }).click();
    await mobile.getByRole('link', { name: 'ML analysis', exact: true }).click();
    await mobile.getByRole('heading', { name: 'Motion analysis', exact: true }).waitFor();
    assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.deepEqual(errors, []);
    const proof = { analysis_id: acceptance.id, frames: job.result.frames.length, candidates: job.result.candidates.length,
      model: job.result.model.model_id, positive: true, real_png_loaded: true, heuristic_comparison: true,
      empty: true, missing_download_error: true, desktop_mobile_navigation: true, javascript_errors: errors };
    fs.writeFileSync('/tmp/spaceapps-ml-browser-prod-proof.json', JSON.stringify(proof, null, 2));
    console.log(JSON.stringify(proof, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
