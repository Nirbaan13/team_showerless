import { test, expect, type Page } from '@playwright/test';

const inventory = ['irsa-spherex', 'cadc', 'eso'].map(id => ({ id, capabilities: {
  product_kinds: ['image'], original: true, cutout: true, availability: 'available', time_filter: 'exact_utc',
  restrictions: id === 'irsa-spherex' ? [] : ['Native products only; instrument processing is unqualified'],
} }));
const observation = (id: string, date = '2002-10-10T01:02:03Z') => ({
  id, frame_id: id, provider: 'cadc', collection: 'HST', native_id: `HST/${id}`, product_kind: 'image', mission: 'HST', instrument: 'NICMOS',
  time: { start_utc: date, end_utc: date, quality: 'verified', native: {} }, observation_date: date,
  original: true, cutout: true, is_available: true, analysisEligible: false, native: {}, provenance: { archive: 'cadc' },
});
const success = (records = [observation('server-a'), observation('server-b', '2002-10-10T04:05:06Z')]) => ({
  observations: records, returned_count: records.length,
  outcomes: [{ provider: 'cadc', status: records.length ? 'success' : 'empty', record_count: records.length, completeness: 'complete', warnings: [], has_continuation: false }],
});
async function backend(page: Page) {
  const state = { queries: [] as URL[], selections: [] as unknown[], polls: [] as string[], analyses: 0, previews: 0,
    result: success(), searchHttpStatus: 200, status: 'preparing', preview: 'unavailable', eligible: false };
  const job = () => ({ id: 'download-opaque', status: state.status, status_url: '/api/observations-download/status-from-server?proof=preserved',
    events_url: '/api/observations-download/download-opaque/events', mode: 'default', query: { observation_ids: ['server-a'], delivery: { mode: 'original' } },
    observations: [observation('server-a')], chunks: [{ id: 'chunk-a', frame_id: 'server-a', status: state.status === 'completed' ? 'ready' : 'pending',
      preview_status: state.preview, image_url: '/api/observations-download/chunks/chunk-a/preview', fits_cutout_url: '/api/native-file-from-server' }],
    progress: { discovery_complete: true, total_chunks: 1, ready_chunks: state.status === 'completed' ? 1 : 0, failed_chunks: 0, unavailable_chunks: 0 }, errors: [],
    assets: state.status === 'completed' ? [{ record_id: 'server-a', status: 'ready', asset: { id: 'chunk-a', bytes: 2880, sha256: 'a'.repeat(64), compression: 'native', analysisEligible: state.eligible, artifact_url: '/api/native-file-from-server' }, provenance: {} }] : [],
  });
  await page.route(/^https:\/\//, r => r.abort());
  await page.route('**/api/motion/**', r => r.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
  await page.route('**/api/catalogue/**', r => r.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
  await page.route('**/backend/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname.replace(/^\/backend/, '');
    if (path === '/api/archives') return route.fulfill({ json: inventory });
    if (path === '/api/observations-search') {
      state.queries.push(url);
      return route.fulfill({ status: state.searchHttpStatus, json: state.searchHttpStatus === 200 ? state.result : { code: 'archive_timeout', message: 'Archive metadata request timed out', retryable: true } });
    }
    if (path === '/api/observations-download') {
      state.selections.push(route.request().postDataJSON());
      return route.fulfill({ status: 202, json: job() });
    }
    if (path === '/api/observations-download/status-from-server') { state.polls.push(url.search); return route.fulfill({ json: job() }); }
    if (path === '/api/observations-download/chunks/chunk-a/preview') {
      state.previews++;
      // A protocol fixture, not evidence of a real HST rendering operation.
      return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=', 'base64') });
    }
    if (path.includes('/analyses/')) state.analyses++;
    return route.fulfill({ status: 503, json: { code: 'unavailable', message: 'Unavailable' } });
  });
  return state;
}
async function open(page: Page, url = '/?tab=viewer') {
  await page.goto(url);
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
}
async function fields(page: Page) {
  await page.getByLabel('RA (deg)', { exact: true }).fill('53.1625');
  await page.getByLabel('Dec (deg)', { exact: true }).fill('-27.7914');
  await page.getByLabel('Archive', { exact: true }).selectOption('cadc');
  await page.getByLabel('Observed from', { exact: true }).fill('1990-01-01');
  await page.getByLabel('Observed through', { exact: true }).fill('2009-12-31');
}
async function apply(page: Page) { await page.getByRole('button', { name: 'Update Field', exact: true }).click(); }

test('applies source, historical dates and enclosing field radius atomically without downloading', async ({ page }) => {
  const state = await backend(page); await open(page); await fields(page); await apply(page);
  await expect(page.getByRole('region', { name: 'Archive observations', exact: true })).toBeVisible();
  await expect(page.getByText('HST/server-a', { exact: true })).toBeVisible();
  const params = state.queries[0].searchParams;
  expect(Object.fromEntries(params)).toMatchObject({ providers: 'cadc', declination_deg: '-27.7914', observed_after: '1990-01-01T00:00:00.000Z', observed_before: '2010-01-01T00:00:00.000Z', product_kinds: 'image' });
  expect(Number(params.get('right_ascension_deg'))).toBeCloseTo(53.1625, 8);
  expect(Number(params.get('radius_degrees'))).toBeGreaterThan(0.05892);
  expect(Number(params.get('radius_degrees'))).toBeLessThan(0.05893);
  expect(state.selections).toHaveLength(0); expect(state.analyses).toBe(0);
  await expect(page.getByRole('button', { name: /^Band 6/ })).toBeDisabled();
  await expect(page.getByText('Coordinate ML Ready', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Play Movie', exact: true })).toHaveCount(0);
});

test('invalid date order prevents a query and explains the field error', async ({ page }) => {
  const state = await backend(page); await open(page); await fields(page);
  await page.getByLabel('Observed from', { exact: true }).fill('2011-01-01'); await apply(page);
  await expect(page.getByRole('alert').filter({ hasText: 'Observed from must be on or before' })).toBeVisible();
  expect(state.queries).toHaveLength(0); expect(state.selections).toHaveLength(0);
});

test('empty results remain genuinely empty without invented dates, candidates or images', async ({ page }) => {
  const state = await backend(page); state.result = success([]); await open(page); await fields(page); await apply(page);
  await expect(page.getByText('No observations found for this region and period.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Download selected/ })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Archive observations' }).locator('img')).toHaveCount(0);
  expect(state.analyses).toBe(0);
});

test('HTTP 200 provider failure and unsupported filters never become no-coverage success', async ({ page }) => {
  const state = await backend(page); state.result = { ...success([]), outcomes: [
    { provider: 'cadc', status: 'failed', record_count: 0, completeness: 'unknown', warnings: ['Provider deadline exceeded'], has_continuation: false },
    { provider: 'eso', status: 'unsupported_filter', record_count: 0, completeness: 'unknown', warnings: ['Exact UTC filter unsupported'], has_continuation: false },
  ] };
  await open(page); await fields(page); await apply(page);
  await expect(page.getByText('cadc: failed', { exact: true })).toBeVisible();
  await expect(page.getByText('eso: unsupported_filter', { exact: true })).toBeVisible();
  await expect(page.getByText('No observations found for this region and period.', { exact: true })).toHaveCount(0);
  expect(state.selections).toHaveLength(0);
});

test('truncation remains visible alongside usable records', async ({ page }) => {
  const state = await backend(page); state.result.outcomes[0].completeness = 'truncated';
  await open(page); await fields(page); await apply(page);
  await expect(page.getByText(/Results are incomplete \(truncated\)/)).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Select observation HST/server-a', exact: true })).toBeEnabled();
});

test('downloads exactly selected IDs, follows the supplied status URL, and does not claim a preview or ML', async ({ page }) => {
  const state = await backend(page); await open(page); await fields(page); await apply(page);
  await page.getByRole('checkbox', { name: 'Select observation HST/server-a', exact: true }).check();
  await page.getByRole('button', { name: 'Download selected (1)', exact: true }).click();
  await expect(page.getByText('Download: preparing', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /^Download native file/ })).toHaveCount(0);
  expect(state.selections).toEqual([{ observation_ids: ['server-a'], delivery: { mode: 'original' } }]);
  state.status = 'completed';
  await expect(page.getByText('Download: completed', { exact: true })).toBeVisible();
  expect(state.polls).toContain('?proof=preserved');
  await expect(page.getByRole('link', { name: /^Download native file/ })).toHaveAttribute('href', /\/backend\/api\/native-file-from-server$/);
  await expect(page.getByText(/Preview unavailable:/)).toBeVisible();
  await expect(page.getByText('ML unavailable for this product; no analysis was started.', { exact: true })).toBeVisible();
  expect(state.previews).toBe(0); expect(state.analyses).toBe(0);
});

test('honors an advertised ready preview instead of treating FITS readiness as preview readiness', async ({ page }) => {
  const state = await backend(page); state.status = 'completed'; state.preview = 'ready';
  await open(page); await fields(page); await apply(page);
  await page.getByRole('checkbox', { name: 'Select observation HST/server-a', exact: true }).check();
  await page.getByRole('button', { name: 'Download selected (1)', exact: true }).click();
  await expect(page.getByRole('img', { name: 'Archive preview HST/server-a', exact: true })).toBeVisible();
  await expect.poll(() => page.getByRole('img', { name: 'Archive preview HST/server-a', exact: true }).evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(1);
  expect(state.previews).toBe(1); expect(state.analyses).toBe(0);
});

test('applied source and dates survive share/reload without fabricated restored results', async ({ page }) => {
  const state = await backend(page); await open(page); await fields(page); await apply(page);
  await expect(page).toHaveURL(/archive=cadc/);
  await expect(page).toHaveURL(/observed_through=2009-12-31/);
  await page.reload(); await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await expect(page.getByLabel('Archive', { exact: true })).toHaveValue('cadc');
  await expect(page.getByLabel('RA (deg)', { exact: true })).toHaveValue('53.162500');
  await expect(page.getByLabel('Dec (deg)', { exact: true })).toHaveValue('-27.791400');
  await expect(page.getByLabel('Observed from', { exact: true })).toHaveValue('1990-01-01');
  await expect(page.getByLabel('Observed through', { exact: true })).toHaveValue('2009-12-31');
  await expect(page.getByRole('region', { name: 'Archive observations' }).getByText('HST/server-a', { exact: true })).toHaveCount(0);
  await apply(page); await expect(page.getByText('HST/server-a', { exact: true })).toBeVisible();
  expect(Number(state.queries.at(-1)!.searchParams.get('right_ascension_deg'))).toBeCloseTo(53.1625, 8);
  expect(Number(state.queries.at(-1)!.searchParams.get('declination_deg'))).toBeCloseTo(-27.7914, 8);
  expect(state.analyses).toBe(0);
});

test('a new failing query clears the previous selection, native links and observations', async ({ page }) => {
  const state = await backend(page); state.status = 'completed'; await open(page); await fields(page); await apply(page);
  await page.getByRole('checkbox', { name: 'Select observation HST/server-a', exact: true }).check();
  await page.getByRole('button', { name: 'Download selected (1)', exact: true }).click();
  await expect(page.getByRole('link', { name: /^Download native file/ })).toBeVisible();
  state.searchHttpStatus = 504;
  await page.getByLabel('Archive', { exact: true }).selectOption('eso');
  await page.getByLabel('RA (deg)', { exact: true }).fill('120'); await apply(page);
  await expect(page.getByRole('alert').filter({ hasText: 'archive_timeout' }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: /^Download native file/ })).toHaveCount(0);
  await expect(page.getByText('HST/server-a', { exact: true })).toHaveCount(0);
  expect(state.analyses).toBe(0);
});


test('uses server eligibility per record rather than hardcoding every archive ineligible', async ({ page }) => {
  const state = await backend(page); state.result.observations[0].analysisEligible = true;
  await open(page); await fields(page); await apply(page);
  await expect(page.getByRole('row').filter({ hasText: 'HST/server-a' })).toContainText('Analysis eligible · not run');
  await expect(page.getByRole('row').filter({ hasText: 'HST/server-b' })).toContainText('ML unavailable: instrument/product is not qualified');
  expect(state.analyses).toBe(0);
});

test('calendar date boundaries use UTC across leap day', async ({ page }) => {
  const state = await backend(page); await open(page); await fields(page);
  await page.getByLabel('Observed from', { exact: true }).fill('2000-02-29');
  await page.getByLabel('Observed through', { exact: true }).fill('2000-02-29');
  await apply(page); await expect(page.getByText('HST/server-a', { exact: true })).toBeVisible();
  expect(state.queries[0].searchParams.get('observed_after')).toBe('2000-02-29T00:00:00.000Z');
  expect(state.queries[0].searchParams.get('observed_before')).toBe('2000-03-01T00:00:00.000Z');
});


test('embed and full-app links preserve the applied archive and observation period', async ({ page }) => {
  await backend(page); await open(page); await fields(page); await apply(page);
  await expect(page.getByText('HST/server-a', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Embed', exact: true }).click();
  const snippet = await page.locator('pre').textContent();
  expect(snippet).toContain('archive=cadc'); expect(snippet).toContain('observed_from=1990-01-01');
  expect(snippet).toContain('observed_through=2009-12-31');
  const src = snippet!.match(/src="([^"]+)"/)![1];
  await page.goto(src);
  const full = page.getByRole('link', { name: 'Open Full App ↗', exact: true });
  await expect(full).toHaveAttribute('href', /archive=cadc/);
  await expect(full).toHaveAttribute('href', /observed_through=2009-12-31/);
  expect(new URL((await full.getAttribute('href'))!).searchParams.has('embed')).toBe(false);
});
