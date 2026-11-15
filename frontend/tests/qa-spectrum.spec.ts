import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

const measured = {
  target: 'Measured target', ra: 166.79, dec: 5.29, aperture_radius_pix: 2,
  subtraction_mode: 'zodi_subtracted', bad_pixel_mask: 'Measured mask', wcs_mode: 'WCS-WAVE',
  molecular_detections: [], detectors_summary: {}, total_channels: 1,
  spectrum: [{ channel: 1, detector: 'D6', detector_array: 6, wavelength_um: 4.5,
    bandwidth_um: .04, flux_mjy: 1.25, uncertainty_mjy: .1, snr: 12.5, flagged: false, mjd: 61023.5 }],
};
async function openSpectrum(page: Page, state: { failed: boolean; empty?: boolean }) {
  await page.route('https://**', route => route.abort());
  await page.route('**/api/catalogue/**', route => route.fulfill({ status: 503, json: {} }));
  await page.route('**/api/motion/**', route => route.fulfill({ status: 503, json: {} }));
  await page.route('**/backend/**', route => route.fulfill({ status: 503, json: {} }));
  await page.route('**/api/spectrum?**', route => state.failed
    ? route.fulfill({ status: 502, json: { code: 'pipeline_unavailable', message: 'Measurement service unavailable' } })
    : route.fulfill({ json: state.empty ? { ...measured, total_channels: 0, spectrum: [] } : measured }));
  await page.goto('/?tab=viewer&preset=3i-atlas');
  await page.getByRole('button', { name: 'Scientist', exact: true }).click();
  await page.getByRole('button', { name: 'Spectral Analysis', exact: true }).click();
}

test('QA-002 failed measurement never enables exporting generated science', async ({ page }) => {
  await openSpectrum(page, { failed: true });
  await expect(page.getByRole('button', { name: 'Measure IRSA', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Export CSV', exact: true })).toBeDisabled();
  await expect(page.getByText('102 Bands Calibrated', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Demonstration Model Profile', { exact: false })).toHaveCount(0);
  await expect(page.getByText('Detected Molecular Absorption Features', { exact: true })).toHaveCount(0);
});

test('QA-002 measured export contains only returned channels and retry failure clears them', async ({ page }) => {
  const state = { failed: false };
  await openSpectrum(page, state);
  await expect(page.getByRole('button', { name: 'Export CSV', exact: true })).toBeEnabled();
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV', exact: true }).click();
  const csv = readFileSync((await (await downloaded).path())!, 'utf8');
  expect(csv).toContain('1,D6,4.5,0.04,1.25,0.1,12.5');
  expect(csv).not.toContain('DEMONSTRATION_MODE');
  expect(csv).not.toContain('Water Ice');
  state.failed = true;
  await page.getByRole('button', { name: 'Measure IRSA', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Measure IRSA', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Export CSV', exact: true })).toBeDisabled();
});

test('QA-002 empty measured channels and molecular detections remain empty', async ({ page }) => {
  await openSpectrum(page, { failed: false, empty: true });
  await expect(page.getByRole('button', { name: 'Measure IRSA', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Export CSV', exact: true })).toBeDisabled();
  await expect(page.getByText('102 Bands Calibrated', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Detected Molecular Absorption Features', { exact: true })).toHaveCount(0);
});
