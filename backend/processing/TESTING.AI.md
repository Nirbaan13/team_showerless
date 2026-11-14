# Offline FITS worker verification

Verified on 2026-11-14 using `/home/usatovpavel/edu/UtilsAI/.venv/bin/python`
(Python 3.14, Astropy 8.0.2, NumPy 2.5.3, Pillow 12.3).

## Protocol

Run `python backend/processing/worker.py`, write one JSON object to stdin, close
stdin. Stdout contains exactly one JSON result and a newline. Exit 0 means success;
exit 1 means an error. Diagnostics go to stderr. No HTTP server, archive lookup,
alignment module, download, or procedural image fallback is imported.

Requests:

```json
{"operation":"capabilities"}
{"operation":"preview","image_path":"/absolute/raw-or-clean.fits","output_path":"/absolute/new.png"}
{"operation":"zodi","image_path":"/absolute/raw.fits","output_path":"/absolute/new-clean.fits"}
{"operation":"spectrum","image_path":"/absolute/raw.fits","ra_deg":129.369570729,"dec_deg":-37.9181394302,"radius_pix":2.0}
```

Output paths must not exist and must have an existing parent directory. The caller
owns atomic publication. Source paths are read-only. Requests are limited to
16,384 bytes; FITS input/output to 256 MiB; images to 4096 by 4096 pixels. Radius
must be positive and at most 64 pixels; RA is [0,360), declination [-90,90].

Capabilities result:

```json
{"status":"ok","operations":["preview","zodi"],"spectrum":{"status":"not_ready","code":"missing_pixel_spectral_calibration"}}
```

Both successful image operations return `status`, `operation`, `output_path`,
`width`, `height`, `masked_pixels`, `data_min`, `data_max`, `data_unit` (`MJy/sr`),
and `subtraction` (`raw_calibrated` or `zodi_subtracted`). Preview adds `stretch`
(`zscale`), `stretch_min`, and `stretch_max`. Min/max describe finite unflagged
physical pixels before display stretching. Masked PNG pixels are transparent.

Error shape is `{"status":"error","error":{"code":"...","message":"..."}}`.
A science gate also provides `error.reason`. Codes include `invalid_request`,
`invalid_input`, `invalid_output`, `invalid_fits`, `missing_hdu`, `invalid_shape`,
`invalid_flags`, `unsupported_unit`, `nonfinite_data`, `no_valid_pixels`,
`already_processed`, `invalid_variance`, `not_ready`, and `processing_failed`.

## Scientific behavior and provenance

Preview renders the existing IMAGE array, masks NaNs/infinities and the team's
bad FLAGS bits (3655), and applies ZScale. It does not subtract ZODI, including
when the input is already processed. The numeric source data is never modified.

ZODI calls `spherex.cleaning.load_clean_cutout` after validating IMAGE, FLAGS,
VARIANCE, ZODI, matching dimensions, and compatible units at the same numerical
scale. IMAGE becomes the team's masked IMAGE-ZODI in float64. Other HDU arrays and
spatial WCS are retained. Checksums are regenerated. Provenance in IMAGE:
`ZODISUB=True`, `SPXPROC='zodi-v1'`, `HIERARCH SPX SOURCE SHA256`, and HISTORY.
Repeating ZODI on marked input fails `already_processed`. Only recognized markers
can identify previously processed external files; trusted callers must retain
this provenance and must supply original raw FITS for future spectral work.
VARIANCE is preserved, without adding ZODI model uncertainty. This operation is
model subtraction and masking, without reprojection, tiling, or alignment.

## Verification evidence

`python -m pytest -q`: 31 tests passed. Tests use actual on-disk FITS fixtures and
actual subprocess CLI calls, PNG byte decoding, raw versus processed pixel values,
NaN/flag masks, preservation, missing/malformed inputs, output protection, bounds,
unit/shape/variance checks, and the explicit spectrum gate. The test import also
checks that service, query, and alignment modules have not been imported.

The deterministic committed `backend/src/test/resources/processing/native_fixture.fits`
is 8x8, raw IMAGE=10 except [4,4]=20, ZODI=2, FLAGS=0, VARIANCE=1,
ICRS center RA=1/Dec=2, detector 1, MJD-OBS=60000. Expected processed IMAGE is
8 except [4,4]=18. Regenerate with the shared interpreter and
`backend/processing/tests/generate_native_fixture.py`.

Live smoke used both immutable `/tmp/spaceapps-live-irsa-service/raw/*.fits` files
(2040x2040). Original source SHA256 values were unchanged after preview and ZODI:

| Cache file prefix | Masked pixels | Raw min/max MJy/sr | Processed min/max MJy/sr |
| --- | ---: | --- | --- |
| c014a9c5 | 55,400 | -17.03858566 / 93.95430756 | -17.15910643 / 93.84201603 |
| c9f3069a | 119,894 | -19.14758682 / 91.71855927 | -19.26789192 / 91.60966571 |

Each preview took approximately 2.5 seconds; each ZODI operation 1.4 seconds.
Every valid output pixel was compared exactly against float64 IMAGE-ZODI, and
PRIMARY/IMAGE/FLAGS/VARIANCE/ZODI/EPSF/WCS-WAVE were preserved. Scratch artifacts
were written only under `/tmp/spaceapps-verified-worker-*`.

## Spectrum remains unavailable

The team `measure_cutout_point` and `extract_spectrum` execute on real cached FITS.
At RA=129.369570729, Dec=-37.9181394302 on c014a9c5, radius=2:
MJD=60794.59416296, detector=1, wavelength=0.9042 um, bandwidth=0.023 um,
flux=4.011827850511499 mJy, uncertainty=0.07749043565963326 mJy, SNR=51.77.
These are runtime characterization values, not validated science products.

A controlled spatial plus WAVE-TAB fixture independently checks the conversion:
five 1-arcsec-square pixels sum to 95 MJy/sr, giving 2.232920901214299 mJy;
variance sum 20 gives uncertainty 0.10511500891568655 mJy. One image produces
one observed point. No missing channels are synthesized. Off-image and flagged
apertures are skipped by the team function. Negative variance produces a NaN
uncertainty upstream; the worker rejects invalid variance before any measurement.

[Official IRSA product documentation](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
states that WCS-WAVE is intended for visualization, and science analysis requires
CWAVE and CBAND from the matched Spectral WCS calibration product. Both cached
images lack those layers. Spectrum requests fail `not_ready` with reason
`missing_pixel_spectral_calibration`. Adding layers alone does not enable spectra:
the reason becomes `unverified_spectral_photometry`. Calibration association,
aperture/PSF correction, local background, detector pixel solid-angle variation
(the team uses a single projected area), and uncertainty propagation remain
unvalidated. No public scientific spectrum or 102-band completeness is claimed.
