import { expect, test } from '@playwright/test';

const record = { id: 'PX-000001', name: 'Registry target', ra: 166.79, dec: 5.29, candidate_type: 'moving_object', status: 'under_review', snr: 8, speed_arcsec_hr: 2, fit_rms_px: 0.3, epoch_count: 4, spectral_summary: {}, metadata: {}, discovery_date: '2025-12-14T11:01:45Z', created_at: '2025-12-14T11:01:45Z', updated_at: '2025-12-14T11:01:45Z', fixed_stack_url: '', motion_stack_url: '', detection_method: 'heuristic_leave_one_out' };

test('an unavailable registry never claims persisted seed candidates or votes', async ({ page }) => {
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { message: 'Unavailable' } }));
  await page.goto('/?tab=catalogue');
  await expect(page.getByRole('alert').filter({ hasText: 'Registry unavailable' })).toBeVisible();
  await expect(page.getByText('PX-000001', { exact: true })).toHaveCount(0);
  await expect(page.getByText('WAL SQLite Persisted', { exact: true })).toHaveCount(0);
});

test('list and dossier preserve zero server votes and unknown validation', async ({ page }) => {
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/catalogue/candidates') return route.fulfill({ json: { candidates: [{ ...record, consensus_summary: { total_votes: 0, likely_real_votes: 0, likely_artifact_votes: 0, positive_percentage: 0 } }], total: 1 } });
    if (url.pathname === '/api/catalogue/candidates/PX-000001') return route.fulfill({ json: { ...record, classifications: [], validation_checks: [], external_submissions: [] } });
    return route.fulfill({ status: 503, json: { message: 'Unavailable' } });
  });
  await page.goto('/?tab=catalogue');
  await expect(page.getByText('0% Real (0 votes)', { exact: true })).toBeVisible();
  await page.getByText('PX-000001', { exact: true }).click();
  await expect(page.getByText('(0 independent reviews)', { exact: true })).toBeVisible();
  await expect(page.getByText('Passed', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Pending', { exact: true })).toHaveCount(4);
});

test('discussion uses registry consensus and offers no simulated peer votes', async ({ page }) => {
  const writes: string[] = [];
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    if (route.request().method() !== 'GET') writes.push(route.request().url());
    if (new URL(route.request().url()).pathname === '/api/catalogue/candidates/PX-000001') return route.fulfill({ json: { ...record, classifications: [], validation_checks: [], external_submissions: [] } });
    return route.fulfill({ status: 503, json: { message: 'Unavailable' } });
  });
  await page.goto('/?tab=viewer&preset=3i-atlas');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByRole('button', { name: /Chat & Confirm/ }).click();
  await expect(page.getByText('Registry consensus: 0 persisted confirmations', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Reach 10/ })).toHaveCount(0);
  expect(writes).toHaveLength(0);
});

test('dossier links retain the requested registry identity after reload and sharing', async ({ page }) => {
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    const id = new URL(route.request().url()).pathname.match(/^\/api\/catalogue\/candidates\/(PX-\d+)$/)?.[1];
    if (id) return route.fulfill({ json: { ...record, id, name: `Dossier ${id}`, classifications: [], validation_checks: [], external_submissions: [] } });
    return route.fulfill({ status: 503, json: { message: 'Unavailable' } });
  });
  await page.addInitScript(() => { Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (text: string) => { (window as any).copiedPermalink = text; } } }); });
  await page.goto('/?tab=catalogue&candidate=PX-000004');
  await expect(page.getByRole('heading', { name: 'Dossier PX-000004', exact: true })).toBeVisible();
  await expect(page).toHaveURL(/candidate=PX-000004/);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Dossier PX-000004', exact: true })).toBeVisible();
  await page.getByRole('button', { name: /Share|Permalink|Copy Link/i }).first().click();
  await expect.poll(() => page.evaluate(() => (window as any).copiedPermalink)).toContain('candidate=PX-000004');
});

test('opening a qualified discussion and waiting never dispatches a submission', async ({ page }) => {
  const writes: string[] = [];
  await page.clock.install();
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    if (route.request().method() !== 'GET') writes.push(route.request().url());
    if (new URL(route.request().url()).pathname === '/api/catalogue/candidates/PX-000001') return route.fulfill({ json: { ...record, classifications: [], validation_checks: [], external_submissions: [], consensus: { total_votes: 12, likely_real: 12, likely_artifact: 0, uncertain: 0, already_known: 0, positive_ratio: 1, artifact_ratio: 0, level1_qualified: true, level2_qualified: true, checks_passed: true, validation_summary: {} } } });
    return route.fulfill({ status: 503, json: { message: 'Unavailable' } });
  });
  await page.goto('/?tab=viewer&preset=3i-atlas');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByRole('button', { name: /Chat & Confirm/ }).click();
  await expect(page.getByRole('button', { name: 'Dispatch to MPC / TNS', exact: true })).toBeVisible();
  await page.clock.fastForward(20000);
  await expect(page.getByRole('button', { name: 'Dispatch to MPC / TNS', exact: true })).toBeVisible();
  expect(writes).toHaveLength(0);
});
