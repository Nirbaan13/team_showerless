# Tools for archive image unification

Research date: 2026-11-15. Repository baseline: 44cc7e3. Purpose: provide actual
machine-readable image data to ML across downloaded archives, not rename files or
turn preview PNGs into calibrated observations. User authorizes a new module in the
current Python pipeline container and the Scala processing client, with a new PR.

## Findings from the current system

The federated archive currently downloads native SPHEREx/ESO/CADC FITS images and
LAMOST spectra. FITS is a container, not a common pixel or calibration schema.
Real live download probes produced a primary-HDU CADC image of7x7 and an ESO image
extension of42x42. Their HDUs, pixel scale, WCS and units must be decoded rather
than assumed. Spectra/catalogue products must not be admitted as image planes.

The production ML preparation accepts only named presets or SPHEREx-native FITS.
It assumes IMAGE/FLAGS/VARIANCE/ZODI, SPHEREx flags and detector identities. Its
preset reader hardcodes four known datasets, historical grid conventions and
mission metadata. Feeding foreign data through a preset name would invent facts.

The genuine public numerical consumer is
`ml_inference.detector.find_candidates(images, times)`, also exposed by its NPZ
CLI. It needs a registered epoch/y/x stack and times in hours. This provides a
real interoperability test without changing frozen model artifacts or granting
foreign images automatic production-analysis eligibility.

## Evaluated tools

| Tool | Role | Decision |
| --- | --- | --- |
| Astropy FITS/WCS/units/time | Decode primary/extension/tile-compressed FITS, scaling, celestial coordinates, units and observation times | Use; already pinned in the current scientific runtime |
| Astropy CCDData/NDData | Unified in-memory data, mask, uncertainty and WCS concepts | Follow its explicit data/mask/unit semantics; a small versioned artifact is easier to validate across HTTP than serializing Python objects |
| SciPy ndimage / NumPy | Bounded numerical resampling and array storage, same ecosystem as current ML | Use; implement explicit bilinear weights so masks and independent-pixel variance use their correct weighting |
| reproject | Interpolated, adaptive and spherical-overlap reprojection, output footprints | Strong alternative for general sky reprojection; ordinary interpolation is not flux-conserving, and uncertainty propagation still needs a defined contract. Do not add a second resampling policy silently to existing ML |
| NumPy NPZ/NPY | Typed numerical arrays loaded without pickle | Use NPZ for the current bounded32-frame/512-pixel ML workload and a JSON manifest; validate ZIP members/expansion before loading |
| Zarr | Chunked persistent arrays and parallel/larger-than-memory access | Useful for larger future datasets; adds storage/protocol complexity not needed for the present bounded single-VPS artifact |
| ASDF | Rich scientific metadata, array blocks and serialization extensions | Useful for richer scientific interchange; unnecessary runtime/extension coupling for the current NumPy consumer |
| Pillow | Decode ordinary PNG/JPEG/TIFF input assets | Support an explicitly non-astrometric pixel-grid path. Preserve that previews lack demonstrated scientific calibration/time/WCS |

Astropy applies FITS BSCALE/BZERO when loading data. Header dimensions must be
checked before allocation, and externally compressed input must have an expanded
byte limit. Tile compression and primary versus extension images need separate
fixtures. Multiple plausible image HDUs or cube planes require explicit selection.

Sky-grid unification is a WCS transformation, not image resize. A fixed ICRS TAN
grid gives consistent orientation and pixel scale. Bilinear interpolation is a
point-sampled transformation, not integrated-flux or PSF matching; the manifest
must say so. Invalid pixels and uncovered areas are explicit masks. Independent
variance uses squared normalized interpolation weights; output covariance is not
represented and must be declared. Unit conversion is allowed only where actual
metadata supports it; counts/ADU cannot become flux without calibration.

NPZ stores numerical NPY arrays in a ZIP container. Avoid object arrays, disable
pickle and bound both compressed and declared expanded sizes. Missing dates,
uncertainties or unit calibration remain missing, never zero-valued measurements
or download timestamps presented as exposure times.

## Selected implementation boundary

Create an independent `pipeline/unification` module with FITS/raster decoding,
registered-grid conversion, provenance, bounded NPZ export and a matching ML
loader. Add HTTP application composition around the existing service rather than
rewriting the team's current cleaning/spectral functions. Scala resolves only
server-issued completed archive assets/native chunks, snapshots their exact bytes,
passes relative shared-volume manifests and owns durable public jobs/artifact URLs.

Export `images[frame,y,x]` with NaN at invalid positions, explicit masks/coverage,
optional variance with a known-value mask, true observation times and frame IDs,
WCS/units/bands/instrument provenance, plus an optional tensor representation.
A pixel-grid raster dataset remains distinguishable from a registered sky dataset.
The loader must reject incompatible/missing temporal/photometric context before
calling the existing motion detector, while general numeric tensors remain usable
for ML models that explicitly accept those inputs.

## Sources

- [Astropy scaled and compressed image data](https://docs.astropy.org/en/stable/io/fits/usage/image.html)
- [Astropy CCDData](https://docs.astropy.org/en/stable/nddata/ccddata.html)
- [Astropy unit equivalencies](https://docs.astropy.org/en/stable/units/equivalencies.html)
- [reproject celestial image algorithms](https://docs.astropy.org/projects/reproject/en/stable/celestial.html)
- [reproject footprint meaning](https://docs.astropy.org/projects/reproject/en/stable/footprints.html)
- [reproject adaptive flux units](https://reproject.readthedocs.io/en/stable/reference/adaptive_options.html)
- [NumPy compressed numerical archives](https://numpy.org/doc/stable/reference/generated/numpy.savez_compressed.html)
- [NumPy safe loading and size controls](https://numpy.org/doc/stable/reference/generated/numpy.load.html)
- [Zarr arrays](https://zarr.readthedocs.io/en/stable/user-guide/arrays/)
- [ASDF](https://www.asdf-format.org/projects/asdf/en/stable/)
