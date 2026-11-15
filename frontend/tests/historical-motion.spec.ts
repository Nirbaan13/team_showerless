import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

// Protocol fixtures only; real-pixel acceptance is recorded separately.
const records = [2010, 2014, 2024].map((year, index) => ({
  id: `epoch-${index}`, frame_id: `epoch-${index}`, provider: 'unwise-neo11', collection: 'neo11', version: 'neo11',
  native_id: `1334m076:w2:e00${index}`, product_kind: 'image', mission: 'WISE/NEOWISE', instrument: 'WISE',
  original: true, cutout: false, analysisEligible: true, is_available: true,
  time: { start_utc: `${year}-05-01T00:00:00Z`, end_utc: `${year}-05-02T00:00:00Z`, quality: 'verified' },
  native: { coadd_id: '1334m076', epoch: String(index), band: '2', FILTER: 'W2', release: 'neo11', pixel_scale_arcsec: '2.75' },
  provenance: { release: 'neo11', analysis_profile: 'unwise' },
}));
const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=';
const uuid = '12345678-1234-1234-1234-123456789abc';
const review = {
  id: uuid, unification_id: uuid, profile: 'stellar_proper_motion', target: null, detector: null,
  source: 'unWISE neo11 W2 time-resolved visit coadds', width: 110, height: 110, pixel_scale_arcsec: 2.75,
  retains_outliers: false, has_ephemeris: false, ephemeris_match_tolerance_px: null, simulated_training_fields: null,
  omitted_frame_checks: [], frames: records.map(record => ({ id: record.id, time: record.time.start_utc, coverage: 0.9, aligned: png, residual: png })),
  tracks: [{ id: 'track-1', rank: 1, method: 'heuristic_leave_one_out', random_forest_rank: null,
    epochs: [0, 1, 2], positions_xy: [[20, 20], [30, 30], [50, 50]], sky_deg: [[133, -7], [133, -7], [133, -7]],
    snr: [6, 7, 8], speed_px_per_time: 0.0005, proper_motion_arcsec_per_year: 12.1, proper_motion_unit: 'arcsec/year',
    fit_rms_px: 0.2, known_match: false, max_offset_px: null, ephemeris_offsets_px: null, filter_support: null,
    outlier_at_position: null, fixed_stack: png, motion_stack: png, stack_contributing_exposures: 3 }],
  bloom_tracks: [], comparison: { shared_median: { candidates: 0, match: null }, leave_one_out: { candidates: 1, match: null },
    outliers_masked: null, random_forest: null, bloom: null },
  historical_preparation: { limitations: ['Artifact/outlier/bloom evidence is unavailable.'], warnings: [] },
};

async function setup(page: Page) {
  const state = { selections: [] as unknown[], preparations: [] as unknown[], searches: [] as unknown[],
    polls: [] as string[], failed: false, empty: false, invalid: false, missingScience: false, missingCoverage: false, pending: false,
    releasePreparation: () => {}, pollFinished: false };
  const job = () => ({ id: 'download-job', status: 'completed', status_url: '/api/observations-download/download-job',
    events_url: '/api/observations-download/download-job/events', observations: records,
    chunks: records.map(record => ({ id: `chunk-${record.id}`, frame_id: record.id, status: 'ready', preview_status: 'unavailable', image_url: '', fits_cutout_url: '' })),
    progress: { discovery_complete: true, total_chunks: 12, ready_chunks: 12, failed_chunks: 0, unavailable_chunks: 0 }, errors: [],
    assets: records.flatMap(record => ['#this', '#inverse-variance', '#coverage', '#contributors']
      .filter(role => !(state.missingScience && role === '#this') && !(state.missingCoverage && role === '#coverage')).map((role, i) => ({
      record_id: record.id, status: 'ready', provenance: { asset_role: role },
      // Generic stored files are not qualified here; the observation owns eligibility.
      asset: { id: i ? `aux-${record.id}-${i}` : `science-${record.id}`, artifact_url: '', analysisEligible: false },
    }))),
  });
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/motion/**', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
  await page.route('**/api/catalogue/**', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
  await page.route('**/backend/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname.replace(/^\/backend/, '');
    if (path === '/api/archives') return route.fulfill({ json: ['irsa-spherex', 'unwise-neo11'].map(id => ({ id,
      capabilities: { product_kinds: ['image'], original: true, cutout: false, availability: 'available', time_filter: 'exact_utc', restrictions: [] } })) });
    if (path === '/api/observations-search') return route.fulfill({ json: {
      observations: state.invalid ? records.map((r, i) => i === 2 ? { ...r, native: { ...r.native, coadd_id: '1335m076' } } : r) : records,
      returned_count: 3, outcomes: [{ provider: 'unwise-neo11', status: 'success', record_count: 3, completeness: 'complete', warnings: [], has_continuation: false }],
    } });
    if (path === '/api/observations-download') { state.selections.push(route.request().postDataJSON()); return route.fulfill({ status: 202, json: job() }); }
    if (path === '/api/image-unifications') {
      state.preparations.push(route.request().postDataJSON());
      return route.fulfill({ status: 202, json: { id: uuid, status: 'queued', status_url: `/api/image-unifications/${uuid}?server=1` } });
    }
    if (path === `/api/image-unifications/${uuid}`) {
      state.polls.push(url.search);
      if (state.pending) await new Promise<void>(resolve => { state.releasePreparation = resolve; });
      await route.fulfill({ json: { id: uuid, status: state.failed ? 'failed' : 'completed',
        status_url: `/api/image-unifications/${uuid}?server=1`, ...(state.failed ? { error: { code: 'invalid_source', message: 'Coverage checksum changed' } } : {}) } });
      state.pollFinished = true;
      return;
    }
    if (path === '/api/motion/search') {
      state.searches.push(route.request().postDataJSON());
      return route.fulfill({ json: state.empty ? { ...review, tracks: [] } : review });
    }
    return route.fulfill({ status: 503, json: { code: 'unavailable', message: 'Unavailable' } });
  });
  await page.goto('/?tab=viewer');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByLabel('RA (deg)', { exact: true }).fill('167.205');
  await page.getByLabel('Dec (deg)', { exact: true }).fill('5.148');
  await page.getByLabel('Archive', { exact: true }).selectOption('unwise-neo11');
  const period = page.locator('#tutorial-target-epoch');
  if (await period.getAttribute('open') === null) await period.locator('summary').click();
  await page.getByLabel('Observed from', { exact: true }).fill('2010-01-01');
  await page.getByLabel('Observed through', { exact: true }).fill('2024-12-31');
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  return state;
}
async function selectAndDownload(page: Page) {
  for (const record of records) await page.getByRole('checkbox', { name: `Select observation ${record.native_id}`, exact: true }).check();
  await page.getByRole('button', { name: 'Download selected (3)', exact: true }).click();
  await expect(page.getByText('Download: completed', { exact: true })).toBeVisible();
}

test('prepares only downloaded science assets then displays actual W2 dates, unknown masks and yearly speed', async ({ page }) => {
  const state = await setup(page);
  const run = page.getByRole('button', { name: 'Find historical motion', exact: true });
  await expect(run).toBeDisabled();
  await selectAndDownload(page); await expect(run).toBeEnabled(); await run.click();
  await expect(page.getByRole('region', { name: 'Historical motion result' })).toBeVisible();
  expect(state.preparations).toEqual([{ inputs: records.map(r => ({ kind: 'archive_asset', id: `science-${r.id}` })),
    grid: { kind: 'sky', width: 110, height: 110, ra_degrees: expect.closeTo(167.205, 8), dec_degrees: 5.148, pixel_scale_arcsec: 2.75 },
    options: { normalization: 'none', mask_policy: 'science' } }]);
  expect(state.polls).toEqual(['?server=1']);
  expect(state.searches).toEqual([{ unification_id: uuid, profile: 'stellar_proper_motion' }]);
  const result = page.getByRole('region', { name: 'Historical motion result' });
  await expect(result.getByText('12.10″/year', { exact: true })).toBeVisible();
  await expect(result.getByText('Outlier evidence unavailable', { exact: true })).toBeVisible();
  await expect(result.getByRole('button', { name: /2024-05-01/ })).toBeVisible();
  await expect(result.getByText('Outliers Masked', { exact: true })).toHaveCount(0);
  await expect(result.getByRole('img', { name: /unWISE neo11 W2/ }).first()).toHaveAttribute('src', png);
  const downloaded = page.waitForEvent('download');
  await result.getByRole('button', { name: 'Export candidate JSON', exact: true }).click();
  const path = await (await downloaded).path();
  const exported = JSON.parse(await readFile(path!, 'utf8'));
  expect(exported).toMatchObject({ proper_motion_arcsec_per_year: 12.1, proper_motion_unit: 'arcsec/year', retains_outlier_pixels: null });
  expect(exported).not.toHaveProperty('speed_arcsec_per_hour');
  expect(exported.detections[0]).toMatchObject({ utc_midpoint: '2010-05-01T00:00:00Z', near_outlier_pixel: null });
  await page.getByRole('checkbox', { name: `Select observation ${records[0].native_id}`, exact: true }).uncheck();
  await expect(result).toHaveCount(0);
});

test('preparation failures remain errors and a later query clears the result', async ({ page }) => {
  const state = await setup(page); await selectAndDownload(page); state.failed = true;
  await page.getByRole('button', { name: 'Find historical motion', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Coverage checksum changed' })).toBeVisible();
  expect(state.searches).toHaveLength(0);
  await expect(page.getByRole('region', { name: 'Historical motion result' })).toHaveCount(0);
  state.failed = false; state.empty = true;
  await page.getByRole('button', { name: 'Find historical motion', exact: true }).click();
  await expect(page.getByText('No tracks passed the current thresholds.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Historical motion result' })).toHaveCount(0);
});

test('mixed tiles cannot start historical inference even after successful download', async ({ page }) => {
  const state = await setup(page); state.invalid = true;
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  await selectAndDownload(page);
  await expect(page.getByRole('button', { name: 'Find historical motion', exact: true })).toBeDisabled();
  await expect(page.getByText(/Select distinct epochs of the same unWISE neo11 W2 tile/)).toBeVisible();
  expect(state.preparations).toHaveLength(0);
});

test('completed auxiliary files cannot substitute for a server-issued science asset', async ({ page }) => {
  const state = await setup(page); state.missingScience = true;
  await selectAndDownload(page);
  await expect(page.getByRole('button', { name: 'Find historical motion', exact: true })).toBeDisabled();
  await expect(page.getByText(/Every selected observation needs one completed, qualified science asset/)).toBeVisible();
  expect(state.preparations).toHaveLength(0);
});

test('missing associated coverage blocks preparation even when the job reports completed', async ({ page }) => {
  const state = await setup(page); state.missingCoverage = true;
  await selectAndDownload(page);
  await expect(page.getByRole('button', { name: 'Find historical motion', exact: true })).toBeDisabled();
  await expect(page.getByText(/Every selected observation needs one completed coverage product/)).toBeVisible();
  expect(state.preparations).toHaveLength(0);
});

test('applying another query aborts a pending preparation before it can trigger inference', async ({ page }) => {
  const state = await setup(page); state.pending = true;
  await selectAndDownload(page);
  await page.getByRole('button', { name: 'Find historical motion', exact: true }).click();
  await expect.poll(() => state.polls.length).toBe(1);
  await page.getByLabel('RA (deg)', { exact: true }).fill('168');
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Find historical motion', exact: true })).toBeDisabled();
  state.releasePreparation();
  await expect.poll(() => state.pollFinished).toBe(true);
  expect(state.searches).toHaveLength(0);
  await expect(page.getByRole('region', { name: 'Historical motion result' })).toHaveCount(0);
});
