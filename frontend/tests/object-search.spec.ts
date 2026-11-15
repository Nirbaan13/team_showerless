import { expect, test, type Page } from '@playwright/test';

// Exercise the application and its real acquisition client. Only the remote
// archive boundary is replaced, so a stored preset cannot satisfy a search.
async function setup(page: Page) {
  const requests: URL[] = [];
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/api/archives')) return route.fulfill({ json: ['irsa-spherex', 'cadc'].map(id => ({
      id, capabilities: { product_kinds: ['image'], original: true, cutout: true, availability: 'available', time_filter: 'exact_utc', restrictions: [] },
    })) });
    if (url.pathname.endsWith('/api/observations/default') || url.pathname.endsWith('/api/observations-search')) requests.push(url);
    if (url.pathname.endsWith('/api/observations-search')) return route.fulfill({ json: {
      observations: [], returned_count: 0,
      outcomes: [{ provider: 'cadc', status: 'empty', record_count: 0, completeness: 'complete', warnings: [], has_continuation: false }],
    } });
    return route.fulfill({ status: 502, json: { code: 'archive_http_error', message: 'Archive returned HTTP 502', retryable: true } });
  });
  await page.goto('/?tab=viewer');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  return requests;
}

test('selecting a known star performs a real request and retries without switching to a stored preset', async ({ page }) => {
  const requests = await setup(page);
  await page.getByRole('button', { name: 'Find object', exact: true }).click();
  await page.getByRole('combobox', { name: 'Object name', exact: true }).fill('barnard');
  await page.getByRole('option', { name: "Barnard's Star", exact: true }).click();
  await expect.poll(() => requests.length).toBe(1);
  expect(Number(requests[0].searchParams.get('right_ascension_deg'))).toBeCloseTo(269.4462908, 6);
  expect(Number(requests[0].searchParams.get('declination_deg'))).toBeCloseTo(4.7679166, 6);
  await expect(page.getByRole('alert').filter({ hasText: 'Archive returned HTTP 502' }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Find object', exact: true })).toHaveAttribute('aria-expanded', 'false');
  expect(new URL(page.url()).searchParams.get('object')).toBe('barnard');
  expect(new URL(page.url()).searchParams.has('preset')).toBe(false);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(() => requests.length).toBe(2);
  await page.getByRole('button', { name: /^Band 2/ }).click();
  await expect.poll(() => requests.length).toBe(3);
  expect(requests[2].searchParams.get('detector_array')).toBe('2');
  expect(new URL(page.url()).searchParams.has('preset')).toBe(false);
});

test('keyboard name filtering searches the chosen object through the existing SPHEREx route', async ({ page }) => {
  const requests = await setup(page);
  await page.getByRole('button', { name: 'Find object', exact: true }).click();
  const input = page.getByRole('combobox', { name: 'Object name', exact: true });
  await expect(input).toBeFocused();
  await input.fill('40 eri');
  await expect(page.getByRole('listbox', { name: 'Objects', exact: true }).getByRole('option')).toHaveCount(1);
  await input.press('ArrowDown');
  await input.press('Enter');
  await expect.poll(() => requests.length).toBe(1);
  expect(Object.fromEntries(requests[0].searchParams)).toMatchObject({
    detector_array: '6',
  });
  expect(Number(requests[0].searchParams.get('right_ascension_deg'))).toBeCloseTo(63.8245827, 6);
  expect(Number(requests[0].searchParams.get('declination_deg'))).toBeCloseTo(-7.6821341, 6);
  expect(requests[0].pathname).toMatch(/api\/observations\/default$/);
  await expect(page.getByRole('button', { name: 'Update Field', exact: true })).toBeVisible();
});

test('unknown names and dismissal never submit coordinates or claim image availability', async ({ page }) => {
  const requests = await setup(page);
  const trigger = page.getByRole('button', { name: 'Find object', exact: true });
  await trigger.click();
  const options = page.getByRole('listbox', { name: 'Objects', exact: true }).getByRole('option');
  await expect(options).toHaveCount(10);
  const input = page.getByRole('combobox', { name: 'Object name', exact: true });
  await input.fill('no-such-object-123');
  await expect(options).toHaveCount(0);
  await expect(page.getByText('No matching objects', { exact: true })).toBeVisible();
  await input.press('Enter');
  expect(requests).toHaveLength(0);
  await input.press('Escape');
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await trigger.click();
  await page.getByLabel('RA (deg)', { exact: true }).click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  expect(requests).toHaveLength(0);
});

test('manual coordinate entry clears the searched object identity', async ({ page }) => {
  const requests = await setup(page);
  await page.getByRole('button', { name: 'Find object', exact: true }).click();
  await page.getByRole('option', { name: 'LAWD 37', exact: true }).click();
  await expect.poll(() => requests.length).toBe(1);
  await expect(page).toHaveURL(/object=lawd-37/);
  await page.reload();
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await expect(page.getByLabel('RA (deg)', { exact: true })).toHaveValue('176.473864');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(() => requests.length).toBe(2);
  await page.getByLabel('RA (deg)', { exact: true }).fill('250');
  await page.getByLabel('Dec (deg)', { exact: true }).fill('10');
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  await expect.poll(() => requests.length).toBe(3);
  expect(new URL(page.url()).searchParams.has('object')).toBe(false);
});

test('the square object trigger and its dropdown remain usable in mobile controls', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests = await setup(page);
  await page.getByRole('button', { name: 'Controls', exact: true }).click();
  const trigger = page.getByRole('button', { name: 'Find object', exact: true });
  const box = await trigger.boundingBox();
  expect(box).not.toBeNull();
  expect(Math.abs(box!.width - box!.height)).toBeLessThan(2);
  await trigger.click();
  const list = page.getByRole('listbox', { name: 'Objects', exact: true });
  await expect(list).toBeVisible();
  const bounds = await list.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await page.getByRole('combobox', { name: 'Object name', exact: true }).fill('wolf');
  await page.getByRole('option', { name: 'Wolf 28', exact: true }).click();
  await expect.poll(() => requests.length).toBe(1);
  await expect(page.getByRole('button', { name: 'Close & Return', exact: true })).toBeHidden();
});

test('an all-detector link keeps the chosen object coordinates until an individual band is selected', async ({ page }) => {
  const requests = await setup(page);
  await page.goto('/?tab=viewer&detector=all');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByRole('button', { name: 'Find object', exact: true }).click();
  await page.getByRole('option', { name: "Barnard's Star", exact: true }).click();
  await expect(page.getByLabel('RA (deg)', { exact: true })).toHaveValue('269.446291');
  await expect(page.getByLabel('Dec (deg)', { exact: true })).toHaveValue('4.767917');
  expect(requests).toHaveLength(0);
  await page.getByRole('button', { name: /^Band 2/ }).click();
  await expect.poll(() => requests.length).toBe(1);
  expect(Number(requests[0].searchParams.get('right_ascension_deg'))).toBeCloseTo(269.4462908, 6);
  expect(Number(requests[0].searchParams.get('declination_deg'))).toBeCloseTo(4.7679166, 6);
});
