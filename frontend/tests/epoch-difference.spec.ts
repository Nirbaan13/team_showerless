import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

// Use an actual packaged benchmark bitmap at the HTTP boundary; exercise the
// real application, polling, canvas and empty/error UI, never replace components.
const reviews = JSON.parse(readFileSync(new URL('../public/motion/review.json', import.meta.url), 'utf8'));
const png = Buffer.from(reviews[0].frames[0].residual.split(',')[1], 'base64');
const releases = new Set<() => void>();
test.afterEach(() => { for (const release of releases) release(); releases.clear(); });

async function backend(page: Page, options: { download?: string; analysis?: string; missingDifference?: boolean; brokenBitmap?: boolean; delayBitmap?: boolean; ra?: number; withCandidate?: boolean; missingStacks?: boolean; htmlPreparation?: boolean } = {}) {
  const state = { download: options.download ?? 'completed', analysis: options.analysis ?? 'completed', analysisStarts: 0, prepareCalls: 0, requests: [] as string[], brokenBitmap: options.brokenBitmap ?? false, queries: [] as Record<string, string>[] };
  let releaseBitmap!: () => void;
  const bitmapGate = new Promise<void>(resolve => { releaseBitmap = resolve; });
  releases.add(releaseBitmap);
  if (!options.delayBitmap) releaseBitmap();
  await page.route('https://**', route => route.abort());
  await page.route('**/api/catalogue/**', route => route.fulfill({ status: 503, json: { message: 'Unavailable' } }));
  await page.route('**/detect', route => route.fulfill({ status: 503, json: { message: 'Unavailable' } }));
  await page.route('**/api/motion/**', route => route.fulfill({ status: 503, json: { detail: 'Motion service unavailable' } }));
  await page.route('**/backend/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/backend/, '');
    state.requests.push(path);
    if (path === '/api/observations/default') {
      state.prepareCalls++;
      state.queries.push(Object.fromEntries(url.searchParams));
      expect(Number(url.searchParams.get('right_ascension_deg'))).toBeCloseTo(options.ra ?? 250, 8);
      if (options.htmlPreparation) return route.fulfill({ contentType: 'text/html', body: '<html><body>Static homepage</body></html>' });
      return route.fulfill({ status: 202, json: { id: 'download-test' } });
    }
    if (path === '/api/downloads/download-test') return route.fulfill({ json: {
      id: 'download-test', status: state.download, mode: 'default', query: { right_ascension_deg: 250, declination_deg: 10 },
      observations: [], chunks: [0, 1, 2].map(i => ({ id: `chunk-${i}`, frame_id: `frame-${i}`, status: state.download === 'completed' ? 'ready' : 'pending', preview_status: 'unavailable', image_url: '', fits_cutout_url: `/api/chunks/chunk-${i}` })),
      progress: { discovery_complete: state.download !== 'failed', total_chunks: state.download === 'failed' ? 0 : 3, ready_chunks: state.download === 'completed' ? 3 : 0, failed_chunks: 0, unavailable_chunks: 0 },
      errors: state.download === 'failed' ? [{ code: 'archive_timeout', message: 'Archive metadata request timed out', retryable: true }] : [],
      status_url: '/api/downloads/download-test', events_url: '/api/downloads/download-test/events',
    } });
    const frames = [0, 1, 2].map(i => ({ frame_id: `frame-${i}`, observation_id: `observation-${i}`, midpoint_utc: `2025-12-14T1${i}:00:00Z`, width: 256, height: 144, detector: 6, release: 'QR3', image_url: `/api/analyses/analysis-test/resources/frame-${i}.png`, difference_url: options.missingDifference ? '' : `/api/analyses/analysis-test/resources/difference-${i}.png`, coverage_fraction: 1, outlier_fraction: 0 }));
    const candidates = options.withCandidate ? [{ id: 'track-test', rank: 1, method: 'heuristic_leave_one_out', score: 0.7, score_kind: 'ranking', baseline_score: 2, baseline_rank: 1, right_ascension_deg: 250, declination_deg: 10, coordinate_epoch_utc: '2025-12-14T10:00:00Z', speed_arcsec_per_hour: 2, fit_rms_px: 0.2,
      detections: frames.map((f, i) => ({ frame_index: i, frame_id: f.frame_id, midpoint_utc: f.midpoint_utc, x: 100+i, y: 100, right_ascension_deg: 250, declination_deg: 10, residual_snr: 5, warnings: [] })), warnings: [],
      ...(!options.missingStacks ? { stationary_stack_url: '/api/analyses/analysis-test/resources/candidate-000-stationary.png', moving_stack_url: '/api/analyses/analysis-test/resources/candidate-000-moving.png' } : {}),
    }] : [];
    const job = { id: 'analysis-test' , status: state.analysis, download_id: 'download-test', status_url: '/api/analyses/analysis-test', events_url: '/api/analyses/analysis-test/events',
      ...(state.analysis === 'failed' ? { error: { code: 'processing_failed', message: 'Could not compute difference images', retryable: true } } : {}),
      ...(state.analysis === 'completed' ? { result: { schema_version: 1, analysis_id: 'analysis-test', model: { model_id: 'fixture-model', model_family: 'RankNetTreeBoost', sha256: 'a'.repeat(64), score_kind: 'sigmoid_pairwise_utility', score_description: 'Pairwise ranking utility; not a calibrated probability' }, frames, candidates, warnings: [], settings: {}, provenance: {} } } : {}),
    };
    if (path === '/api/analyses/motion') { state.analysisStarts++; return route.fulfill({ status: 202, json: job }); }
    if (path === '/api/analyses/analysis-test') return route.fulfill({ json: job });
    if (path.startsWith('/api/analyses/analysis-test/resources/')) {
      await bitmapGate;
      return state.brokenBitmap ? route.fulfill({ status: 404, json: { code: 'not_found', message: 'Image missing' } }) : route.fulfill({ contentType: 'image/png', body: png });
    }
    return route.fulfill({ status: 503, json: { code: 'unavailable', message: 'Unavailable' } });
  });
  await page.addInitScript(() => {
    const draw = CanvasRenderingContext2D.prototype.drawImage;
    (window as unknown as { drawnImages: string[] }).drawnImages = [];
    CanvasRenderingContext2D.prototype.drawImage = function (...args: unknown[]) {
      const image = args[0] as HTMLImageElement;
      (window as unknown as { drawnImages: string[] }).drawnImages.push(image.src || 'procedural-canvas');
      return Reflect.apply(draw, this, args);
    } as typeof draw;
  });
  return { state, releaseBitmap };
}

async function openViewer(page: Page) {
  await page.goto('/?tab=viewer');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.locator('input[type=text]').nth(0).fill('250');
  await page.locator('input[type=text]').nth(1).fill('10');
  await page.getByRole('button', { name: 'Diff', exact: true }).click();
}
async function search(page: Page) {
  await page.evaluate(() => { (window as unknown as { drawnImages: string[] }).drawnImages = []; });
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
}
const drawn = (page: Page) => page.evaluate(() => (window as unknown as { drawnImages: string[] }).drawnImages);

test('archive_timeout clears demo epochs and candidates and never starts a doomed analysis', async ({ page }) => {
  const { state } = await backend(page, { download: 'failed', analysis: 'failed' });
  await openViewer(page); await search(page);
  await expect(page.getByRole('alert').filter({ hasText: 'archive_timeout' }).first()).toBeVisible();
  await expect(page.getByText('NASA IRSA / SPHEREx Stream', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Coordinate ML Ready', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Play Movie', exact: true })).toBeDisabled();
  await expect(page.getByText(/^Ranked Objects \([1-9]\d*\)$/)).toHaveCount(0);
  await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
  await expect(page.getByText(/Motion cannot be assessed/).first()).toBeVisible();
  expect(state.analysisStarts).toBe(0);
  expect(await drawn(page)).not.toContain('procedural-canvas');
});

test('running analysis remains pending beyond 18 seconds and publishes real difference images afterward', async ({ page }) => {
  await page.clock.install();
  const { state } = await backend(page, { analysis: 'running' });
  await openViewer(page); await search(page);
  await expect.poll(() => state.analysisStarts).toBe(1);
  await page.clock.fastForward(20_000);
  await expect(page.getByText(/Preparing difference images/).first()).toBeVisible();
  await expect(page.getByText('NASA IRSA / SPHEREx Stream', { exact: true })).toHaveCount(0);
  expect(await drawn(page)).not.toContain('procedural-canvas');
  state.analysis = 'completed';
  await expect.poll(async () => (await drawn(page)).some(url => url.endsWith('/difference-0.png'))).toBe(true);
  await expect(page.getByText('NASA IRSA / SPHEREx Stream', { exact: true })).toBeVisible();
  await expect(page.getByText('Frame 1 of 3', { exact: true })).toBeVisible();
});

test('completed analysis without a difference URL shows unavailable instead of a synthetic difference', async ({ page }) => {
  await backend(page, { missingDifference: true });
  await openViewer(page); await search(page);
  await expect(page.getByText('Difference image unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText(/Motion cannot be assessed/).first()).toBeVisible();
  expect(await drawn(page)).not.toContain('procedural-canvas');
  await page.getByRole('button', { name: 'Aligned', exact: true }).click();
  await expect.poll(async () => (await drawn(page)).some(url => url.endsWith('/frame-0.png'))).toBe(true);
});

test('HTTP failure loading the difference bitmap stays explicit and never paints a demo', async ({ page }) => {
  await backend(page, { brokenBitmap: true });
  await openViewer(page); await search(page);
  await expect(page.getByText('Difference image unavailable', { exact: true })).toBeVisible();
  expect(await drawn(page)).not.toContain('procedural-canvas');
});

test('analysis failure stays failed, and Refresh retries the actual request', async ({ page }) => {
  const { state } = await backend(page, { analysis: 'failed' });
  await openViewer(page); await search(page);
  await expect(page.getByRole('alert').filter({ hasText: 'processing_failed' }).first()).toBeVisible();
  await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
  state.analysis = 'completed';
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(async () => (await drawn(page)).some(url => url.endsWith('/difference-0.png'))).toBe(true);
  expect(state.prepareCalls).toBe(2);
});

test('3I/ATLAS preset still displays its actual packaged difference bitmap', async ({ page }) => {
  await backend(page);
  await page.goto('/?tab=viewer&preset=3i-atlas');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByRole('button', { name: 'Diff', exact: true }).click();
  await expect.poll(async () => (await drawn(page)).includes(reviews[0].frames[0].residual)).toBe(true);
  await expect(page.getByText('Difference image unavailable', { exact: true })).toHaveCount(0);
});


test('nearby custom coordinates never borrow unrelated 3I benchmark exposures', async ({ page }) => {
  const { state } = await backend(page, { ra: 167.4, download: 'failed' });
  await openViewer(page);
  await expect.poll(async () => (await drawn(page)).includes(reviews[0].frames[0].residual)).toBe(true);
  await page.locator('input[type=text]').nth(0).fill('167.4');
  await page.locator('input[type=text]').nth(1).fill('5.29');
  await search(page);
  await expect(page.getByRole('alert').filter({ hasText: 'archive_timeout' }).first()).toBeVisible();
  expect(state.prepareCalls).toBe(1);
  await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
});

test('a custom verification target uses its own field and real loading lifecycle', async ({ page }) => {
  const { state } = await backend(page, { download: 'failed' });
  await page.addInitScript(() => localStorage.setItem('spherex_community_comments', JSON.stringify([{ id: 'verification-test', author: 'Test', role: 'Volunteer', timestamp: '2026-01-01T00:00:00Z', candidateId: 'verification-target', message: 'Inspect custom field', vote: 'investigate', upvotes: 0,
    setting: { targetPresetId: null, candidateId: 'verification-target', candidateName: 'Custom test field', ra: 250, dec: 10, fov: "3'", selectedArray: 2, activeFrameIndex: 0, subtractionMode: 'epoch_difference' } }])));
  await page.goto('/?tab=feed');
  await page.getByText('Custom test field', { exact: true }).click();
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'archive_timeout' }).first()).toBeVisible();
  expect(state.queries[0]).toMatchObject({ right_ascension_deg: '250', declination_deg: '10', width_arcmin: '3', height_arcmin: '3', detector_array: '2' });
  await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
});

test('Refresh retries a failed bitmap even when backend dedup returns the same resource URL', async ({ page }) => {
  const { state } = await backend(page, { brokenBitmap: true });
  await openViewer(page); await search(page);
  await expect(page.getByText('Difference image unavailable', { exact: true })).toBeVisible();
  state.brokenBitmap = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(async () => (await drawn(page)).some(url => url.endsWith('/difference-0.png'))).toBe(true);
});

test('candidate evidence displays actual returned stack assets instead of generated proof', async ({ page }) => {
  await backend(page, { withCandidate: true });
  await openViewer(page); await search(page);
  await expect(page.getByAltText('Fixed sky position stack')).toHaveAttribute('src', '/backend/api/analyses/analysis-test/resources/candidate-000-stationary.png');
  await expect(page.getByAltText('Following the fitted track stack')).toHaveAttribute('src', '/backend/api/analyses/analysis-test/resources/candidate-000-moving.png');
  await expect(page.getByText(/Moving Object: Sharpens When Shifted/)).toHaveCount(0);
});

test('missing candidate stack assets are explicitly unavailable', async ({ page }) => {
  await backend(page, { withCandidate: true, missingStacks: true });
  await openViewer(page); await search(page);
  await expect(page.getByText('Stack unavailable', { exact: true })).toHaveCount(2);
  await expect(page.getByAltText('Fixed sky position stack')).toHaveCount(0);
  await expect(page.getByAltText('Following the fitted track stack')).toHaveCount(0);
});


test('a static-site HTML response never becomes fabricated live observations', async ({ page }) => {
  const { state } = await backend(page, { htmlPreparation: true });
  await openViewer(page); await search(page);
  await expect(page.getByRole('alert').filter({ hasText: /invalid response/ }).first()).toBeVisible();
  await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
  expect(state.analysisStarts).toBe(0);
  expect(await drawn(page)).not.toContain('procedural-canvas');
});

test('an explicit preset verification cancels a pending custom analysis and restores preset status', async ({ page }) => {
  const { state } = await backend(page, { analysis: 'running' });
  await page.addInitScript(() => localStorage.setItem('spherex_community_comments', JSON.stringify([{ id: 'preset-verification', author: 'Test', role: 'Volunteer', timestamp: '2026-01-01T00:00:00Z', candidateId: '3I/ATLAS', message: 'Inspect preset', vote: 'investigate', upvotes: 0,
    setting: { targetPresetId: '3i-atlas', candidateId: '3I/ATLAS', candidateName: 'Preset test field', ra: 166.79, dec: 5.29, fov: "5'", selectedArray: 6, activeFrameIndex: 0, subtractionMode: 'epoch_difference' } }])));
  await openViewer(page); await search(page);
  await expect.poll(() => state.analysisStarts).toBe(1);
  await page.getByRole('button', { name: 'Verification Feed', exact: true }).first().click();
  await page.getByText('Preset test field', { exact: true }).click();
  await expect(page.getByText('Benchmark Preset', { exact: true })).toBeVisible();
  await expect.poll(async () => (await drawn(page)).includes(reviews[0].frames[0].residual)).toBe(true);
  state.analysis = 'failed';
  await expect(page.getByText('Coordinate ML failed', { exact: true })).toHaveCount(0);
});


test('stored benchmarks disclose provenance without pretending to run a new model', async ({ page }) => {
  const { state } = await backend(page);
  await page.goto('/?tab=home');
  await page.getByRole('button', { name: /3I\/ATLAS/ }).first().click();
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await expect(page.getByText('Stored benchmark · no new inference', { exact: true })).toBeVisible();
  await expect(page.getByText(/Scoring candidates with Random Forest/)).toHaveCount(0);
  await expect(page.getByText(/(?:Active|Inspect) \(\d+%\)/)).toHaveCount(0);
  await expect(page.getByText('Scores order candidates; they are not discovery probabilities.', { exact: true })).toBeVisible();
  expect(state.analysisStarts).toBe(0);
});

test('live analysis displays the returned model family, ID, score meaning and server ranking', async ({ page }) => {
  await backend(page, { withCandidate: true });
  await openViewer(page); await search(page);
  await expect(page.getByText('fixture-model', { exact: true })).toBeVisible();
  await expect(page.getByText('RankNetTreeBoost', { exact: true })).toBeVisible();
  await expect(page.getByText('sigmoid_pairwise_utility', { exact: true })).toBeVisible();
  await expect(page.getByText('Pairwise ranking utility; not a calibrated probability', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Random Forest', exact: true })).toHaveCount(0);
  await expect(page.getByText('Score 0.700', { exact: true })).toBeVisible();
});


for (const width of [1500, 390]) {
  test(`image metadata stays compact and expandable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await backend(page);
    await page.goto('/?tab=viewer&preset=3i-atlas');
    await page.getByRole('button', { name: 'Scientist', exact: true }).click();
    const details = page.locator('details[aria-label="Image metadata"]');
    await expect(details).toBeVisible();
    await expect(details).not.toHaveAttribute('open', '');
    const compact = await details.boundingBox();
    expect(compact!.height).toBeLessThan(80);
    expect(compact!.width).toBeLessThan(width - 20);
    await details.locator('summary').click();
    await expect(details).toHaveAttribute('open', '');
    await expect(details.getByRole('checkbox', { name: 'Show source labels' })).not.toBeChecked();
    await details.locator('summary').click();
    await page.getByRole('button', { name: 'Zoom In', exact: true }).click();
  });
}


test('same-day visits retain distinct UTC labels and select their actual frames', async ({ page }) => {
  await backend(page);
  await page.goto('/?tab=viewer&preset=3i-atlas');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  for (const [index, time] of ['11:01', '12:39', '17:33', '19:06'].entries()) {
    const visit = page.getByRole('button', { name: `12-14 ${time}z`, exact: true });
    await expect(visit).toHaveAttribute('title', new RegExp(`UTC: 2025-12-14T${time}`));
    await visit.click();
    await expect(page.getByText(`Frame ${index + 1} of 4`, { exact: true })).toBeVisible();
  }
});
