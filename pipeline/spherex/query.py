import os
import time
import astropy.units as u
from astropy.io import fits
from astropy.table import Table
from astroquery.ipac.irsa import Irsa

DEFAULT = os.getenv("SPHEREX_COLLECTION", "spherex_dr1") # Configurable default collection
def list_collections():
    tbl = Irsa.list_collections(servicetype = "SIA", filter ="spherex")
    tbl.pprint(max_lines = -1, max_width = -1)
def _archive_gateway():
    # Repository scripts can run with only pipeline/ on sys.path. A production
    # image must package science/archive_gateway.py alongside pipeline/.
    try:
        from science import archive_gateway
    except ModuleNotFoundError as exc:
        if exc.name != "science":
            raise
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from science import archive_gateway
    return archive_gateway


def image_search(coordinates, deg, collection, *, allow_release_fallback=False):
    if os.getenv("IRSA_DISCOVERY_URL", "").strip():
        archive_gateway = _archive_gateway()
        coord = coordinates.icrs
        found = archive_gateway.discover(coord.ra.deg, coord.dec.deg, deg / 2)
        columns = ("access_url", "energy_bandpassname", "dataproduct_subtype", "t_min",
                   "obs_collection", "frame_id", "observation_date", "source_url", "discovery_source")
        rows = [(i.url, f"SPHEREx-D{i.detector}", "science", i.mjd, f"spherex_{i.release.lower()}",
                 i.frame_id, i.observation_date, i.source_url, i.discovery_source) for i in found
                if allow_release_fallback or collection == f"spherex_{i.release.lower()}"]
        result = Table(rows=rows, names=columns,
                       dtype=("U4096", "U16", "U16", float, "U32", "U2048", "U64", "U4096", "U128"))
        result.sort("t_min")
        result.meta.update(discovery_complete=found.discovery_complete, discovery_source=found.discovery_source)
        return result
    res = Irsa.query_sia(pos=(coordinates, deg/2 * u.deg), collection = collection)
    if len(res) == 0:
      return res
    if "dataproduct_subtype" in res.colnames:
      res = res[res["dataproduct_subtype"] == "science"]
    if "t_min" in res.colnames:
      res.sort("t_min")
    return res
          
"""Finds overlapping spectral images @ position from IRSA SIA"""
def detector(row):
    for col in ("energy_bandpassname", "instrument_name"):
        if col in row.colnames:
            return str(row[col])
    return ""
def cutout(url, out, retries=3, *, source_url=None, discovery_source="sia"):
    archive_gateway = _archive_gateway()
    for tries in range(1, retries + 1):
        tmp = out.with_suffix(".part")
        try:
            archive_gateway.download_cutout(url, tmp, source_url=source_url,
                                            discovery_source=discovery_source)
            with fits.open(tmp):
                pass  # validate before it enters the cache
            tmp.replace(out)
            return "good"
        except Exception as e:
            if tries == retries or discovery_source == "s3_mirror":
                return f"failure: {e}"
            time.sleep(2 * tries)
        finally:
            tmp.unlink(missing_ok=True)
