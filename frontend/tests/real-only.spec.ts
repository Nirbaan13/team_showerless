import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

// Actual packaged review pixels at the HTTP boundary; this test manifest is not product data.
const review = JSON.parse(readFileSync(new URL('../public/motion/review.json', import.meta.url), 'utf8'))[0];
const previewPng = Buffer.from(review.frames[0].aligned.split(',')[1], 'base64');
const previewHash = createHash('sha256').update(previewPng).digest('hex');
function rawManifest(id: string, count: number) {
  const target = id === 'rw-aurigae'
    ? { id, name: 'RW Aurigae', ra_deg: 76.956417, dec_deg: 30.401444, recommended_detector: 4 }
    : { id, name: 'Epsilon Indi B', ra_deg: 331.044146, dec_deg: -56.782844, recommended_detector: 3 };
  return { schema_version: 1, dataset_kind: 'real_archive', targets: [{ ...target,
    coordinate_note: 'Published reference coordinates; no proper-motion correction was applied.',
    observations: review.frames.slice(0, count).map((frame: any) => ({
      frame_id: frame.id, observation_date: frame.time, detector: target.recommended_detector, release: 'QR2',
      preview_url: `/demo/previews/${frame.id}.png`, fits_url: `/demo/fixture/${frame.id}.fits`,
      source_url: `https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/${frame.id}.fits`,
      source_sha256: 'a'.repeat(64), preview_sha256: previewHash, image_width: review.width, image_height: review.height,
    })) }] };
}

test.skip(process.env.VITE_DEMO_REAL_ONLY !== 'true', 'Run against the explicit real-only build.');

test('star preset links acquire real coordinates and keep archive failure explicit', async ({ page }) => {
  const acquisitions: URL[] = [];
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { message: 'Unavailable' } }));
  await page.route('**/backend/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/api/observations/default')) acquisitions.push(url);
    return route.fulfill({ status: 502, json: { code: 'archive_unavailable', message: 'Archive request returned HTTP 502' } });
  });
  await page.goto('/?tab=viewer&preset=barnards-star');
  await expect.poll(() => acquisitions.length).toBeGreaterThan(0);
  expect(Number(acquisitions[0].searchParams.get('right_ascension_deg'))).toBeGreaterThan(269);
  expect(acquisitions[0].searchParams.get('detector_array')).toBe('2');
  expect(acquisitions[0].searchParams.get('width_arcmin')).toBe('12');
  await expect(page.getByRole('button', { name: "12'", exact: true })).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.get('fov')).toBe("12'");
  await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
  await expect(page.getByText(/any of the 6 Benchmark Presets/)).toHaveCount(0);
  await expect(page.getByText(/Motion cannot be assessed/).first()).toBeVisible();
  await expect(page.getByText('Candidate IR Flare Anomaly', { exact: false })).toHaveCount(0);
});

test('stored review discussion has no fictitious peer confirmations or automatic registry identity', async ({ page }) => {
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => route.fulfill({ json: [] }));
  await page.goto('/?tab=viewer&preset=3i-atlas');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByRole('button', { name: /Chat & Confirm/ }).click();
  await expect(page.getByText('No Notes Logged Yet', { exact: true })).toBeVisible();
  await expect(page.getByText('Registry consensus unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Dr. Elena Rostova', { exact: false })).toHaveCount(0);
});

test('catalogue dossier does not request synthetic pixels and displays absent metrics as unavailable', async ({ page }) => {
  const requests: string[] = [];
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    if (path === '/api/catalogue/candidates/PX-000001') return route.fulfill({ json: {
      id: 'PX-000001', name: 'User recorded candidate', ra: 1, dec: 2, candidate_type: 'moving_object', status: 'under_review',
      snr: null, speed_arcsec_hr: null, fit_rms_px: null, epoch_count: 0, spectral_summary: {}, metadata: {},
      discovery_date: '2025-12-14', created_at: '2025-12-14', updated_at: '2025-12-14',
      fixed_stack_url: '/api/motion/coadd/PX-000001/fixed.png', motion_stack_url: '/api/motion/coadd/PX-000001/motion.png',
      detection_method: 'volunteer_blink', classifications: [], validation_checks: [], external_submissions: [],
    } });
    return route.fulfill({ status: 503, json: { message: 'Unavailable' } });
  });
  await page.goto('/?tab=catalogue&candidate=PX-000001');
  await expect(page.getByRole('heading', { name: 'User recorded candidate', exact: true })).toBeVisible();
  await expect(page.getByText('Fixed sky stack unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Motion stack unavailable', { exact: true })).toBeVisible();
  expect(requests.some(path => path.startsWith('/api/motion/coadd/') || path === '/api/motion/cutout/render')).toBe(false);
  expect(await page.locator('img[src^="data:image/svg"]').count()).toBe(0);
});

for (const [id, count] of [['rw-aurigae', 1], ['epsilon-indi-b', 2]] as const) {
  test(`${count} packaged real raw frames remain visible without starting motion inference`, async ({ page }) => {
    const backendRequests: string[] = [];
    await page.route(/^https:\/\//, route => route.abort());
    await page.route('**/api/**', route => route.fulfill({ status: 503, json: { message: 'Unavailable' } }));
    await page.route('**/backend/**', route => { if (/\/(observations|analyses|downloads|detect)(?:\/|\?|$)/.test(route.request().url())) backendRequests.push(route.request().url()); return route.fulfill({ status: 503, json: { message: 'No inference available' } }); });
    await page.route('**/demo/preview-manifest.json', route => route.fulfill({ json: rawManifest(id, count) }));
    await page.route('**/demo/previews/**', route => route.fulfill({ contentType: 'image/png', body: previewPng }));
    await page.addInitScript(() => {
      const draw = CanvasRenderingContext2D.prototype.drawImage;
      (window as any).rawPreviewDraws = [];
      CanvasRenderingContext2D.prototype.drawImage = function (...args: any[]) {
        (window as any).rawPreviewDraws.push({ src: args[0].src, width: args[3], height: args[4] });
        return Reflect.apply(draw, this, args);
      } as typeof draw;
    });
    if (count === 1) {
      await page.goto('/');
      await page.getByRole('button', { name: 'RW Aurigae', exact: true }).click();
    } else {
      await page.goto('/?tab=viewer&ra=331.044146&dec=-56.782844&detector=3&fov=12%27');
    }
    await page.getByRole('button', { name: 'Scientist', exact: true }).click();
    await expect(page.getByText(`Frame 1 of ${count}`, { exact: true })).toBeVisible();
    await expect(page.getByText('Packaged real archive data', { exact: true })).toBeVisible();
    await expect(page.getByText(/Motion analysis not run/).first()).toBeVisible();
    await expect(page.getByText(/insufficient.*three observations/i).first()).toBeVisible();
    await expect(page.getByText('Coordinate ML Ready', { exact: true })).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => (window as any).rawPreviewDraws.some((draw: any) => draw.src.includes('/demo/previews/') && draw.width / draw.height === 256 / 144))).toBe(true);
    await expect(page.getByRole('button', { name: 'Diff', exact: true })).toBeDisabled();
    await expect(page.getByRole('checkbox', { name: /ESA Gaia DR3/ })).toBeDisabled();
    await expect(page.getByRole('checkbox', { name: /ESA Gaia DR3/ })).not.toBeChecked();
    await page.getByLabel('Image metadata', { exact: true }).locator('summary').click();
    await expect(page.getByText(`Detector: D${id === 'rw-aurigae' ? 4 : 3}; pixels: 256 × 144`, { exact: true })).toBeVisible();
    await expect(page.getByText('Published reference coordinates; no proper-motion correction was applied.', { exact: true }).first()).toBeVisible();
    if (count === 2) {
      await page.getByRole('button', { name: '12-14 12:39z', exact: true }).click();
      await expect(page.getByText('Frame 2 of 2', { exact: true })).toBeVisible();
      const metadata = page.getByLabel('Image metadata', { exact: true });
      await expect(metadata).toBeVisible();
      if (await metadata.getAttribute('open') === null) await metadata.locator('summary').click();
      await expect(page.getByText(`Observed UTC: ${review.frames[1].time}`, { exact: true })).toBeVisible();
    }
    expect(backendRequests).toEqual([]);
    await expect.poll(() => new URL(page.url()).searchParams.get('fov')).toBe("12'");
    if (count === 2) {
      await page.getByRole('button', { name: "3'", exact: true }).click();
      await page.getByRole('button', { name: 'Update Field', exact: true }).click();
      await expect.poll(() => backendRequests.some(url => url.includes('/api/observations/default') && new URL(url).searchParams.get('width_arcmin') === '3')).toBe(true);
      await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
    }
  });
}

for (const reason of ['fabricated', 'other-field'] as const) {
  test(`a ${reason} manifest cannot replace the requested real archive field`, async ({ page }) => {
    let acquisitions = 0;
    let previewRequests = 0;
    const manifest = rawManifest(reason === 'other-field' ? 'epsilon-indi-b' : 'rw-aurigae', 1);
    if (reason === 'fabricated') manifest.dataset_kind = 'mock';
    await page.route(/^https:\/\//, route => route.abort());
    await page.route('**/api/**', route => route.fulfill({ status: 503, json: { message: 'Unavailable' } }));
    await page.route('**/backend/**', route => {
      if (route.request().url().includes('/api/observations/default')) acquisitions++;
      return route.fulfill({ status: 503, json: { message: 'Actual archive request unavailable' } });
    });
    await page.route('**/demo/preview-manifest.json', route => route.fulfill({ json: manifest }));
    await page.route('**/demo/previews/**', route => { previewRequests++; return route.fulfill({ contentType: 'image/png', body: previewPng }); });
    await page.goto('/?tab=viewer&preset=rw-aurigae');
    await expect.poll(() => acquisitions).toBeGreaterThan(0);
    await expect(page.getByText('No observations loaded', { exact: true })).toBeVisible();
    await expect(page.getByText('Packaged real archive data', { exact: true })).toHaveCount(0);
    expect(previewRequests).toBe(0);
  });
}
