async (page) => {
  const assert = {
    equal(actual, expected) { if (actual !== expected) throw Error(`Expected ${expected}, got ${actual}`); },
    ok(value, message) { if (!value) throw Error(message || 'Expected truthy value'); },
    match(value, pattern) { if (!pattern.test(value)) throw Error(`Unexpected value: ${value}`); },
    deepEqual(actual, expected) { if (JSON.stringify(actual) !== JSON.stringify(expected)) throw Error('Values differ'); }
  };
  const base = 'http://146.103.122.246:8080';
  const api = 'http://146.103.122.246';
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto(base + '/?analysis=1');
  await page.getByRole('heading', {name: 'Motion analysis', exact: true}).waitFor();
  await page.getByText('spherex-pairwise-v4', {exact: true}).waitFor();
  await page.getByText('Detection settings', {exact: true}).click();
  await page.getByLabel('Minimum residual S/N', {exact: true}).fill('4.26374819');
  const admission = page.waitForResponse(response => response.url().endsWith('/api/analyses/motion') && response.request().method() === 'POST');
  await page.getByRole('button', {name: 'Run analysis', exact: true}).click();
  const accepted = await (await admission).json();
  await page.getByRole('heading', {name: /candidate tracks · 4 exposures/}).waitFor({timeout: 120000});
  const job = await (await page.request.get(api + '/api/analyses/' + accepted.id)).json();
  assert.equal(job.status, 'completed');
  assert.equal(job.result.model.sha256, 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35');
  assert.equal(job.result.model.model_family, 'RankNetTreeBoost');
  assert.equal(await page.locator('.inference-candidate').count(), job.result.candidates.length);
  await page.waitForFunction(() => Array.from(document.querySelectorAll('.inference-image img')).every(image => image.complete && image.naturalWidth > 0));
  assert.ok(await page.locator('.inference-image svg circle').count());
  await page.locator('.inference-candidate-list select').selectOption('baseline');
  assert.match(await page.locator('.inference-candidate').first().innerText(), /heuristic #1/);
  await page.getByLabel('Minimum residual S/N', {exact: true}).fill('100');
  await page.getByRole('button', {name: 'Run analysis', exact: true}).click();
  await page.getByRole('heading', {name: '0 candidate tracks · 4 exposures', exact: true}).waitFor({timeout: 120000});
  await page.locator('form select').first().selectOption('download');
  await page.getByLabel('Download ID', {exact: true}).fill('v4-browser-missing-download');
  await page.getByRole('button', {name: 'Run analysis', exact: true}).click();
  await page.getByRole('alert').waitFor();
  assert.match(await page.getByRole('alert').innerText(), /not found/i);
  const viewports = [];
  const browser = page.context().browser();
  for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
    const context = await browser.newContext({viewport});
    try {
      const view = await context.newPage();
      view.on('pageerror', error => errors.push(String(error)));
      await view.goto(base + '/?analysis=1&id=' + job.id);
      await view.getByRole('heading', {name: `${job.result.candidates.length} candidate tracks · 4 exposures`, exact: true}).waitFor();
      const bounds = await view.locator('.inference-page').evaluate(element => ({top: element.getBoundingClientRect().top, bottom: element.getBoundingClientRect().bottom, viewport: innerHeight}));
      assert.ok(bounds.bottom <= viewport.height + 1, JSON.stringify(bounds));
      await view.locator('.inference-page').evaluate(element => {element.scrollTop = element.scrollHeight;});
      const provenance = await view.locator('.inference-limitations').last().boundingBox();
      assert.ok(provenance.y + provenance.height <= viewport.height + 1);
      assert.ok(await view.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      viewports.push({viewport, bounds, provenance_bottom: provenance.y + provenance.height});
    } finally { await context.close(); }
  }
  assert.deepEqual(errors, []);
  return {checked_at_utc: new Date().toISOString(), frontend_base: base, api_base: api,
    analysis_id: job.id, model_sha256: job.result.model.sha256, frames: job.result.frames.length,
    candidates: job.result.candidates.length, real_png_loaded: true, trajectory_overlay: true,
    heuristic_comparison: true, empty: true, missing_download_error: true, viewports, javascript_errors: errors};
}
