import { expect, test } from '@playwright/test';

test('invalid declination keeps the requested field and starts no acquisition', async ({ page }) => {
  const searches: string[] = [];
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    if (route.request().url().includes('/observations/')) searches.push(route.request().url());
    return route.fulfill({ status: 503, json: { message: 'Unavailable' } });
  });
  await page.goto('/?tab=viewer');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  const original = page.url();
  await page.locator('input[type=text]').nth(0).fill('361');
  await page.locator('input[type=text]').nth(1).fill('91');
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  await expect(page.getByText('Declination must be between -90° and +90°', { exact: true })).toBeVisible();
  expect(page.url()).toBe(original);
  expect(searches).toHaveLength(0);
});

test('malformed coordinates are rejected as whole values and RA wrapping is explicit', async ({ page }) => {
  let searches = 0;
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/**', route => {
    if (route.request().url().includes('/observations/')) searches++;
    return route.fulfill({ status: 503, json: { message: 'Unavailable' } });
  });
  await page.goto('/?tab=viewer');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.locator('input[type=text]').nth(0).fill('361');
  await page.locator('input[type=text]').nth(1).fill('10.2.3');
  await page.getByRole('button', { name: 'Update Field', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Enter valid numerical coordinates' })).toBeVisible();
  await expect(page.getByText('RA wraps into [0°, 360°).', { exact: false })).toBeVisible();
  expect(searches).toBe(0);
});
