import { test, expect, type Page } from '@playwright/test';

async function open(page: Page, suffix = '') {
  const calls: URL[] = [];
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    calls.push(new URL(route.request().url()));
    return route.fulfill({ status: 503, json: { code: 'archive_http_error', message: 'Unavailable', retryable: true } });
  });
  await page.goto('/?tab=viewer' + suffix);
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  return calls;
}
const archival = (calls: URL[]) => calls.filter(url => /\/api\/(archives|observations-search|observations-download)(\/|$)/.test(url.pathname));

test('the screenshot archive controls are replaced by one future link without archive requests', async ({ page }) => {
  const calls = await open(page);
  const notice = page.getByRole('link', { name: 'Archive observations In future', exact: true });
  await expect(notice).toBeVisible();
  await expect(notice).toHaveAttribute('href', 'https://github.com/Nirbaan13/team_showerless/pull/38');
  await expect(notice).toHaveText('Archive observationsIn future');
  await expect(page.getByLabel('Archive', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Observation Era', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Observed from', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Time filter: exact_utc/)).toHaveCount(0);
  expect(archival(calls)).toEqual([]);
  await page.locator('#tutorial-target-coords').screenshot({ path: '/tmp/spaceapps-archive-freeze-controls.png' });
});

test('legacy archived observation links cannot start discovery, downloads or historical analysis', async ({ page }) => {
  const calls = await open(page, '&archive=cadc&observed_from=1990-01-01&observed_through=2009-12-31');
  await expect(page.getByRole('link', { name: 'Archive observations In future', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Archive observations', exact: true })).toHaveCount(0);
  expect(archival(calls)).toEqual([]);
  expect(calls.some(url => /historical/.test(url.pathname))).toBe(false);
});

test('Update Field still uses the existing SPHEREx acquisition route', async ({ page }) => {
  const calls = await open(page);
  await page.getByLabel('RA (deg)', { exact: true }).fill('15.25');
  await page.getByLabel('Dec (deg)', { exact: true }).fill('-24.5');
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  await expect.poll(() => calls.filter(url => url.pathname.endsWith('/api/observations/default')).length).toBe(1);
  expect(archival(calls)).toEqual([]);
});
