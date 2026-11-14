# IRSA server-side SPHEREx cutouts

Observation preparation now requests IBE server-side spatial cutouts instead of
transferring a full parent spectral-image file for each small requested field.
Search remains a metadata-only SIA2 query. Existing HTTP/gRPC parameters and
parent frame IDs remain unchanged.

## Spatial behavior

The requested sky polygon/range is enclosed in a spherical cap. A square cutout
covering that cap is requested with `center=<ra>,<dec>deg&size=<diameter>deg`.
This conservatively covers a rectangular field despite the different pixel-axis
orientations of individual exposures. One nominal 6.15-arcsec source pixel is
added per edge to accommodate native-grid rounding. RA wrap and polar centers
are handled with unit vectors; malformed or unrepresentable hemispheric regions
fail explicitly.

IRSA retains native pixels and orientation. The result is a covering rectangle,
not an exact polygon mask, a reprojected mosaic, or an aligned epoch stack. A
source frame can provide only its own overlapping footprint. A requested region
extending across several frames still has one chunk per matching source image.
No small request implies that a single source can provide missing coverage.

Only trusted on-premises `/ibe/data/spherex/` product URLs support this path.
Unsupported locations and failed cutouts return explicit errors; the service
does not silently fall back to downloading a whole image. Full native fetching
remains available to internal archive integrations that explicitly use it.

## Persistence and metadata

The selected cutout URL is persisted per job and included in the existing raw
cache identity. Different geometries therefore cannot reuse an incompatible
cutout. The internal optional `sourceUrl` retains the original IBE URL so a
reference can be selected again for another field without appending parameters
to an earlier subset. Old serialized images without this field remain readable.

The retrieval request-key version changes so previously completed full-frame
jobs cannot satisfy new cutout requests. Historical completed job/chunk URLs
remain usable and retain their original file identity. Cache leases, volume
admission, atomic publication, restart recovery, and byte limits still apply.

Observation/SIA/TAP metadata refer to the parent image. Cached subset FITS headers
are identified by `fits.spatial_subset=true` to distinguish their reduced image
dimensions and WCS from the source product's metadata.

## Evidence

The official [IRSA IBE documentation](https://irsa.ipac.caltech.edu/ibe/cutouts.html)
documents spatial cutouts and native-axis behavior. The SPHEREx
[data access guide](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)
documents the on-premises cutout URL. Discovery stays separate from this file
retrieval operation.

Research on 2026-11-14 obtained a valid 5 x 5 arcmin QR3 cutout of 3,988,800 bytes
from a 66,386,880-byte parent (HEAD only), and a 3 x 5 arcmin cutout of 3,965,760
bytes. Both retained PRIMARY/IMAGE/FLAGS/VARIANCE/ZODI/EPSF/WCS-WAVE. EPSF alone
occupied 3,859,632 data bytes, so tiny angular regions do not imply kilobyte files.
These direct research sizes differ from the deliberately enclosing square used
by the backend.

Final local regression after merging the latest ML and migration changes:
`./sbtw test stage` passed 130 tests with zero failures and one optional live
test ignored. Running `IRSA_CUTOUT_LIVE=1 ./sbtw 'testOnly
spaceapps.IrsaCutoutsLiveSpec'` separately passed against the documented QR3
product: the actual Scala adapter returned a 4,034,880-byte valid MEF containing
seven HDUs. Its covering-square request used a 0.1212677761-degree side. The
primary HDU has no EXTNAME; all six named mission extensions were verified.

The live test uses a known product URL to isolate retrieval from discovery. A
separate full SIA-to-job attempt was accepted with HTTP 202 but failed explicitly
with `archive_timeout` while querying IRSA metadata. It did not transfer a full
image or fabricate a result. This external discovery availability issue remains
independent of the verified cutout transport. A separate red/green recovery
regression verifies that an interrupted legacy job retains already-issued chunk
URLs when its parent products are selected as cutouts during recovery.
Whitespace, shell syntax and YAML
checks passed; independent code review found no blocking issues.
