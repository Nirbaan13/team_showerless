"""Exercise packaged private HTTP operation and its genuine ML data loader."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
import uuid

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from unification.ml import load_bundle


def main():
    root = Path(os.environ.get("UNIFICATION_DATA_ROOT", "/tmp/spherex_cutouts"))
    job_id = str(uuid.uuid4())
    directory = root / "unifications" / job_id
    directory.mkdir(parents=True)
    grid = dict(kind="sky", ra_degrees=120., dec_degrees=-20., width=24, height=24, pixel_scale_arcsec=2.)
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crpix = [12.5, 12.5]
    wcs.wcs.crval = [120., -20.]
    wcs.wcs.cdelt = [-2/3600, 2/3600]
    inputs = []
    try:
        for epoch in range(3):
            source = directory / "inputs" / f"{epoch:03d}.fits"
            source.parent.mkdir(exist_ok=True)
            header = wcs.to_header()
            header["BUNIT"] = "MJy/sr"
            header["FILTER"] = "test-band"
            header["INSTRUME"] = "synthetic-smoke"
            header["TELESCOP"] = "synthetic-smoke"
            header["DATE-AVG"] = f"2026-01-01T0{epoch}:00:00.000"
            fits.PrimaryHDU(np.full((24,24), epoch+1, dtype=np.float32), header).writeto(source)
            inputs.append(dict(id=f"smoke-{epoch}",path=source.relative_to(root).as_posix(),
                sha256=hashlib.sha256(source.read_bytes()).hexdigest(), profile="generic",
                image_hdu=None, plane_indices=[], metadata=dict(provider="smoke",observation_id=f"epoch-{epoch}")))
        payload = dict(schema_version=1, job_id=job_id, inputs=inputs, grid=grid,
                       options=dict(normalization="none", mask_policy="science",target_unit=None))
        request = urllib.request.Request("http://127.0.0.1:8002/internal/image-unifications",
                    data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request, timeout=135) as response:
            result = json.load(response)
        artifact = root / result["bundle"]["path"]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == result["bundle"]["sha256"]
        bundle = load_bundle(artifact)
        images, times = bundle.motion_inputs()
        assert images.shape == (3,24,24) and np.allclose(times,[0,1,2])
        assert np.isfinite(bundle.tensor).all() and result["detection_ready"]
        assert np.allclose(images[:,12,12],[1,2,3])
        print("Packaged image unification HTTP and ML loader smoke passed")
    finally:
        shutil.rmtree(directory)


if __name__ == "__main__":
    main()
